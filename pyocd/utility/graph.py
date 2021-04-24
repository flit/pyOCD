# pyOCD debugger
# Copyright (c) 2019 Arm Limited
# Copyright (c) 2021-2023 Chris Reed
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import threading
import weakref
from contextlib import contextmanager
from typing import (Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Type, Union, cast)

class _PlaneContextStack:
    """@brief Thread-local stack to track currently selected plane."""

    _tls = threading.local()
    _tls.stack = cast(List[str], [])

    @classmethod
    @property
    def current_plane(cls) -> Optional[str]:
        """@brief The topmost plane on the stack."""
        try:
            return cls._tls.stack[-1]
        except IndexError:
            return None

    @classmethod
    def push(cls, plane: str) -> None:
        """@brief Push a new plane to be selected."""
        cls._tls.stack.append(plane)

    @classmethod
    def pop(cls) -> None:
        """@brief Pop the stack.
        @exception IndexError The stack is empty.
        """
        cls._tls.stack.pop()

class GraphNode:
    """@brief Node of the plane DAG.

    All nodes have a parent, which is None for a root node, and zero or more children.
    Nodes optionally have a name, which is usually the same as the multiplane node's name but can
    be changed if necessary.

    Supports indexing and iteration over children.

    Parent and child references point to the GraphNode instance for the referenced node on the same
    plane. To get the node itself, use the @a node attribute.
    """

    __slots__ = ("_node", "_parents", "_children", "__weakref__")

    def __init__(self, node: "MultiGraphNode") -> None:
        """@brief Constructor."""
        super().__init__()
        self._node = weakref.ref(node)
        self._parents: List["GraphNode"] = []
        self._children: List["GraphNode"] = []
        self._node_name: Optional[str] = None

    @property
    def node(self) -> "MultiGraphNode":
        """@brief The graph node of which this plane node is a member.
        @exception RuntimeError Raised if the GraphNode has been deleted.
        """
        # dereference weak ref
        the_node = self._node()
        if not the_node:
            raise RuntimeError("reference to deallocated graph node from plane node")
        return the_node

    @property
    def node_name(self) -> Optional[str]:
        """@brief Name of this graph node.

        Unless this node has a modified name, the value will be the multiplane node's name.
        """
        if self._node_name:
            return self._node_name
        else:
            # We don't have a name, so use the multi-plane node's name.
            try:
                return self.node.node_name
            except RuntimeError:
                return None

    @node_name.setter
    def node_name(self, new_name: str) -> None:
        self._node_name = new_name

    @property
    def parent(self) -> Optional["GraphNode"]:
        """@brief This node's first parent in the plane graph."""
        try:
            return self._parents[0]
        except IndexError:
            return None

    @property
    def parents(self) -> List["GraphNode"]:
        """@brief All parent of this node in the plane graph."""
        return self._parents

    @property
    def children(self) -> List["GraphNode"]:
        """@brief Children of this nodes in the plane graph."""
        return self._children

    @property
    def is_leaf(self) -> bool:
        """@brief Returns true if the node has no children."""
        return len(self.children) == 0

    def add_child(self, node: "GraphNode") -> None:
        """@brief Link a child node onto this object."""
        node._parents.append(self)
        self._children.append(node)

    def find_root(self) -> "GraphNode":
        """@brief Returns the root node of the plane graph."""
        root = self
        while root.parent is not None:
            root = root.parent
        return root

    def find_children(self,
            predicate: Callable[["MultiGraphNode"], bool],
            breadth_first: bool = True
        ) -> Sequence["GraphNode"]:
        """@brief Recursively search for children that match a given predicate.
        @param self
        @param predicate A callable accepting a single argument for the graph node (not the plane node!) to examine.
            If the predicate returns True, then that node is added to the result list and no further searches on that
            node's children are performed. A False predicate result causes the node's children to be searched.
        @param breadth_first Whether to search breadth first. Pass False to search depth first.
        @returns List of matching child plane nodes, or an empty list if no matches were found.
        """
        def _search(node: GraphNode) -> List[GraphNode]:
            results: List[GraphNode] = []
            children_to_examine: List[GraphNode] = []
            for child in node.children:
                if predicate(child.node):
                    results.append(child)
                elif not breadth_first:
                    results.extend(_search(child))
                elif breadth_first:
                    children_to_examine.append(child)

            if breadth_first:
                for child in children_to_examine:
                    results.extend(_search(child))
            return results

        return _search(self)

    def get_first_child_of_type(self, klass: Type[_T]) -> Optional[_T]:
        """@brief Breadth-first search for a child of the given class.
        @param self
        @param klass The class type to search for. The first child at any depth that is an instance
            of this class or a subclass thereof will be returned. Matching children at more shallow
            nodes will take precedence over deeper nodes.
        @returns Either a node object or None.
        """
        matches = self.find_children(lambda c: isinstance(c, klass))
        if len(matches):
            return cast(Optional[_T], matches[0])
        else:
            return None

    def __getitem__(self, key: Union[int, str, slice]) -> Union["GraphNode", List["GraphNode"]]:
        """@brief Returns the child with the given index or node name.

        Slicing is supported with integer indexes.
        """
        if isinstance(key, str):
            # Replace with dict at some point.
            for c in self._children:
                if c.node_name == key:
                    return c
            else:
                raise KeyError(f"no child node with name '{key}'")
        else:
            return self._children[key]

    def __iter__(self) -> Iterator["GraphNode"]:
        """@brief Iterate over the node's children."""
        return iter(self.children)

    def _dump_desc(self) -> str:
        """@brief Similar to __repr__ by used for dump_to_str()."""
        return str(self)

    def dump_to_str(self) -> str:
        """@brief Returns a string describing the object graph."""

        def _dump(node: "GraphNode", level: int) -> str:
            result = ("  " * level) + "- " + node._dump_desc() + "\n"
            for child in node.children:
                result += _dump(child, level + 1)
            return result

        return _dump(self, 0)

    def dump(self) -> None:
        """@brief Pretty print the object graph to stdout."""
        print(self.dump_to_str())

class MultiGraphNode:
    """@brief Multi-plane graph node.

    Nodes belong to one or more independant directed, acyclic graphs, called "planes". Planes are named.
    For each plane, all nodes have one or more parents and zero or more children. The root node's parent is None.
    """

    ## List of all plane names.
    ALL_PLANES = []

    @classmethod
    @contextmanager
    def select_plane(cls, plane: str):
        """@brief Context manager to set the plane for graph operations.

        Any graph operations inside the context, _on the current thread_, will automatically use
        the plane passed in as a parameter.
        """
        try:
            _PlaneContextStack.push(plane)
            yield
        finally:
            _PlaneContextStack.pop()

    def __init__(self) -> None:
        """@brief Graph node constructor."""
        super().__init__()
        self._planes: Dict[str, GraphNode] = {}
        self._node_name: Optional[str] = None

    @property
    def node_name(self) -> Optional[str]:
        """@brief Name of this graph node."""
        return self._node_name

    @node_name.setter
    def node_name(self, new_name: str) -> None:
        self._node_name = new_name

    @property
    def parent(self) -> Optional["MultiGraphNode"]:
        """@brief This node's first parent in the selected plane graph."""
        return self.get_parent()

    @property
    def parents(self) -> List["MultiGraphNode"]:
        """@brief All parent of this node in the selected plane graph."""
        return self.get_parents()

    @property
    def children(self) -> List["MultiGraphNode"]:
        """@brief Children of this nodes in the selected plane graph."""
        return self.get_children()

    def _get_selected_plane(self, explicit_plane: Optional[str]) -> str:
        """@brief Return the name of the plane the caller should use.

        Most methods accept an optional plane name parameter. If this is not provided, the thread-local
        selected plane is used.
        """
        if explicit_plane:
            return explicit_plane
        plane = _PlaneContextStack.current_plane
        if not plane:
            raise ValueError("no plane specified")
        return plane

    def get_plane(self, plane: Optional[str] = None) -> "GraphNode":
        """@brief Return the PlaneNode instance for this node in the specified plane.

        If there isn't already a PlaneNode instance for the plane, one is created.
        """
        plane = self._get_selected_plane(plane)
        try:
            return self._planes[plane]
        except KeyError:
            # Create the new plane node.
            plane_node = GraphNode(self)
            self._planes[plane] = plane_node
            return plane_node

    def get_parent(self, plane: Optional[str] = None) -> Optional["MultiGraphNode"]:
        """@brief This node's first parent in the plane graph."""
        try:
            parent = self.get_plane(plane).parent
            return parent.node if parent else None
        except IndexError:
            return None

    def get_parents(self, plane: Optional[str] = None) -> List["MultiGraphNode"]:
        """@brief All parent of this node in the object graph."""
        return list(self.iter_parents(plane))

    def iter_parents(self, plane: Optional[str] = None) -> Iterator["MultiGraphNode"]:
        """@brief Iterator over all parents on the specified plane."""
        return iter(n.node for n in self.get_plane(plane).parents)

    def get_children(self, plane: Optional[str] = None) -> List["MultiGraphNode"]:
        """@brief Children of this nodes in the object graph."""
        return list(self.iter_children(plane))

    def iter_children(self, plane: Optional[str] = None) -> Iterator["MultiGraphNode"]:
        """@brief Iterator over all children on the specified plane."""
        return iter(n.node for n in self.get_plane(plane))

    def is_leaf_on_plane(self, plane: Optional[str] = None) -> bool:
        """@brief Returns true if the node has no children."""
        return self.get_plane(plane).is_leaf

    def add_child(self, node: "MultiGraphNode", plane: Optional[str] = None) -> None:
        """@brief Link a child node onto this object.

        There is no check for whether the node is already a child, or for potential creation of graph cycles.
        """
        self.get_plane(plane).add_child(node.get_plane(plane))

    def find_root(self, plane: Optional[str] = None) -> "MultiGraphNode":
        """@brief Returns the root node of the object graph."""
        return self.get_plane(plane).find_root().node

    def find_children(self, predicate: Callable[["MultiGraphNode"], bool],
            breadth_first: bool = True, plane: Optional[str] = None) -> List["MultiGraphNode"]:
        """@brief Recursively search for children that match a given predicate.
        @param self
        @param predicate A callable accepting a single argument for the node to examine. If the
            predicate returns True, then that node is added to the result list and no further
            searches on that node's children are performed. A False predicate result causes the
            node's children to be searched.
        @param breadth_first Whether to search breadth first. Pass False to search depth first.
        @returns List of matching child nodes, or an empty list if no matches were found.
        """
        return [pn.node for pn in self.get_plane(plane).find_children(predicate, breadth_first)]

    def get_first_child_of_type(self, klass: Type["MultiGraphNode"], plane: Optional[str] = None) -> Optional["MultiGraphNode"]:
        """@brief Breadth-first search for a child of the given class.
        @param self
        @param klass The class type to search for. The first child at any depth that is an instance
            of this class or a subclass thereof will be returned. Matching children at more shallow
            nodes will take precedence over deeper nodes.
        @returns Either a node object or None.
        """
        matches = self.find_children(lambda c: isinstance(c, klass), plane=plane)
        if len(matches):
            return matches[0]
        else:
            return None

    def __getitem__(self, key: int) -> "MultiGraphNode":
        """@brief Returns the indexed child."""
        return self.get_plane().children[key].node

    def __iter__(self) -> Iterable["MultiGraphNode"]:
        """@brief Iterate over the node's children."""
        return self.iter_children()

    def _dump_desc(self) -> str:
        """@brief Similar to __repr__ but used for dump_to_str()."""
        return str(self)

    def dump_to_str(self, plane: Optional[str] = None) -> str:
        """@brief Returns a string describing the object graph."""

        def _dump(node: "MultiGraphNode", level: int):
            result = ("  " * level) + "- " + node._dump_desc() + "\n"
            for child in node.get_plane().children:
                result += _dump(child.node, level + 1)
            return result

        return _dump(self, 0)

    def dump(self, plane: Optional[str] = None) -> None:
        """@brief Pretty print the object graph to stdout."""
        print(self.dump_to_str(plane))
