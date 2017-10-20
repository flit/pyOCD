#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
 mbed CMSIS-DAP debugger
 Copyright (c) 2006-2013 ARM Limited

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
"""

from __future__ import print_function
import sys
import os
import wx
import wx.lib
from wx.lib.mixins.listctrl import ListCtrlAutoWidthMixin
import wx.stc
import plot
import threading
import numpy
import Queue
import time
from elapsedtimer import ElapsedTimer

# Make disasm optional.
try:
    import capstone
    isCapstoneAvailable = True
except ImportError:
    isCapstoneAvailable = False

sys.path.append('..')
import pyOCD
from pyOCD.debug.elf.decoder import DwarfAddressDecoder

import elapsedtimer
# elapsedtimer.enable = False

kTimestampColumn = 0
kCurrentColumn = 1
kAddressColumn = 2
kFunctionColumn = 3
kFileColumn = 4

targetVdd = 3.0

def sample_to_mA(x):
    return targetVdd*x/0xffff/120.0*1000.0

class DwarfLoaderThread(threading.Thread):
    def __init__(self, elf, completionCallback):
        threading.Thread.__init__(self, name="Processor")
        self._elf = elf
        self._callback = completionCallback
        self._decoder = None
        self.start()

    def run(self):
        self._decoder = DwarfAddressDecoder(self._elf)
        self._callback(self._decoder)

class ProfileData(object):
    def __init__(self):
        self._data = []
        self._graph_data = []
        self._addr = []
        self._callbacks = []
        self._decoder = None
        self._firstTimestamp = 0
        self._lastTimestamp = 0
        self._lastTimestampMicros = 0
        self._lastCurrent = 0
        self._dataLock = threading.RLock()

    @property
    def decoder(self):
        return self._decoder

    def add_update_callback(self, callback):
        self._callbacks.append(callback)

    def set_elf_file(self, elf, callback):
        self._elf_callback = callback
        DwarfLoaderThread(elf, self._dwarf_did_load)

    def _dwarf_did_load(self, decoder):
        self._decoder = decoder
        self._elf_callback()

    def append(self, data):
#         chop = (len(data) + len(self._data) > 10000)
        with self._dataLock:
#             with ElapsedTimer('append %d samples' % len(data)):
            results, graphResults, addrResults = self._process_data(data)
            self._data.extend(results)
            self._graph_data.extend(graphResults)
            self._addr.extend(addrResults)
    #         if chop:
    #             self._data = self._data[-len(data):]
        self._invoke_callbacks()

    def clear(self):
        with self._dataLock:
            self._graph_data = []
            self._data = []
            self._firstTimestamp = 0
            self._lastTimestamp = 0
            self._lastTimestampMicros = 0
            self._lastCurrent = 0
        self._invoke_callbacks()

    def get_count(self):
        with self._dataLock:
            return len(self._data)

    def get_address_for_item(self, index):
        return self._addr[index]

    def get_formatted_item(self, index, column):
        with self._dataLock:
            if column in [kFunctionColumn, kFileColumn]:
                if self._decoder is not None:
                    addr = self._addr[index]
                    if column == kFunctionColumn:
                        fninfo = self._decoder.get_function_for_address(addr)
                        if fninfo is not None:
                            return fninfo.name
                    elif column == kFileColumn:
                        lineinfo = self._decoder.get_line_for_address(addr)
                        if lineinfo is not None:
                            return "%s:%d" % (lineinfo.filename, lineinfo.line)
                return ""
            else:
                if column == kTimestampColumn:
                    value = str(self._data[index][kTimestampColumn])
                elif column == kCurrentColumn:
                    value = "%.3f mA" % self._data[index][kCurrentColumn]
                elif column == kAddressColumn:
                    value = "0x%08x" % self._addr[index]
                else:
                    raise Exception("invalid column number")
                return value

    def find_age_index(self, how_old):
        if not len(self._data):
            return 0
        newestTimestamp = self._data[-1][kTimestampColumn]
        targetTimestamp = newestTimestamp - how_old
        if self._data[0][kTimestampColumn] >= targetTimestamp:
            return 0
        i = len(self._data) - 1
        while (i > 0) and (self._data[i][kTimestampColumn] > targetTimestamp):
            i -= 1
        return i if i >= 0 else 0

    def get_graph_data(self, how_old):
#         with self._dataLock:
#             if not len(self._data):
#                 return []
#             index = self.find_age_index(how_old)
#             return self._data[index:]
        return self._graph_data
#         return self._data

    def graph_index_to_data_index(self, index):
#         return index
        return (index + 1) // 2

    def data_index_to_graph_index(self, index):
        return index * 2 - 1

    def _process_data(self, data):
        results = []
        graphResults = []
        addrResults = []

#         print(data)
        prevTimestampMicros = self._lastTimestampMicros
        prevTimestamp = self._lastTimestamp
        prevCurrent = self._lastCurrent
        badSamples = 0

        for tstamp, addr, current in data:
            current = sample_to_mA(current)

            # Toss garbage samples. Remove when corruption is fixed in DAPLink code.
            if tstamp == 0 or current == 0 or current > 20:
                badSamples += 1
                continue

            saveTimestampMicros = tstamp

            if self._firstTimestamp == 0:
                self._firstTimestamp = tstamp
                tstamp = 0
            elif tstamp < prevTimestampMicros:
                # Handle timestamp wrap
                diff = (1 << 32) - prevTimestampMicros + tstamp
                tstamp = prevTimestamp + (diff / 1000.0)
            else:
                diff = tstamp - prevTimestampMicros
                tstamp = prevTimestamp + (diff / 1000.0)

            results.append((tstamp, current))
            addrResults.append(addr)

            if prevCurrent != 0:
                graphResults.append((tstamp, prevCurrent))
            graphResults.append((tstamp, current))

            prevTimestampMicros = saveTimestampMicros
            prevTimestamp = tstamp
            prevCurrent = current

        if badSamples:
            print("dropped %d corrupt samples out of %d" % (badSamples, len(data)))

        self._lastTimestampMicros = prevTimestampMicros
        self._lastTimestamp = prevTimestamp
        self._lastCurrent = prevCurrent
        return results, graphResults, addrResults

    def _invoke_callbacks(self):
        for cb in self._callbacks:
            cb(self)

class ProfileGraphBuilder(object):
    def __init__(self, data, width, selected):
        self._data = data
        self._width = width
        self._selected_index = selected

    def get_graphics(self):
        self._graph_data = self._data.get_graph_data(self._width)
#         print('graph data is %d samples' % len(self._graph_data))

        lines = plot.PolyLine(self._graph_data, legend='Current (mA)', colour='red')
        allLines = [lines]

        if self._selected_index != -1:
            try:
                index = self._data.data_index_to_graph_index(self._selected_index)
                x = self._graph_data[index][0]
                selectionPoints = [(x,0),(x,10)]
                selectionLine = plot.PolyLine(selectionPoints, colour='gray')

                allLines.append(selectionLine)
            except IndexError:
                pass

        return plot.PlotGraphics(allLines, xLabel='Time (ms)', yLabel='Current (mA)')

    def get_xaxis(self):
        try:
#             startTime = self._graph_data[0][0]
            endTime = self._graph_data[-1][0]
            startTime = endTime - self._width
            if startTime < 0:
                startTime = self._graph_data[0][0]
                endTime = startTime + self._width
            return (startTime, endTime)
        except IndexError:
            return (0, self._width)

class ProcessorThread(threading.Thread):
    def __init__(self, data):
        threading.Thread.__init__(self, name="Processor")
        self.stopFlag = False
        self._data = data
        self._queue = Queue.Queue()

    def run(self):
        while not self.stopFlag:
            try:
                d = self._queue.get(timeout=1)
            except Queue.Empty:
                break
            else:
                self._data.append(d)

    def stop(self):
        self.stopFlag = True

    def push_data(self, data):
        self._queue.put(data)

class ProfilerThread(threading.Thread):
    def __init__(self, board, data):
        threading.Thread.__init__(self, name="Profiler")
        self.board = board
        self.target = board.target
        self.transport = board.transport
        self.stopFlag = False
        self.data = data

#         self.processor_thread = ProcessorThread(self.data)

    def start(self):
#         self.processor_thread.start()
        threading.Thread.start(self)

    def read_vdd(self):
        global targetVdd
        mV = self.transport.getProfilingFeature(2)
        targetVdd = mV / 1000.0
        print("Target Vdd = %f" % targetVdd)

    def start_device(self):
        self.target.resume()

        if not self.is_running():
            print("Target is not running for some reason")
            return

        self.read_vdd()

        self.transport.startProfiling()

        print("Profiling started")

    def is_running(self):
        return self.target.getState() == pyOCD.target.target.TARGET_RUNNING

    def run(self):
        self.start_device()
        while not self.stopFlag:
            self._read_profile_data()
        print("Stopping profiling")
        self.transport.stopProfiling()

    def stop(self):
        self.stopFlag = True
#         self.processor_thread.stop()

    def _read_profile_data(self):
#         with ElapsedTimer('read usb data'):
        data = self.transport.readProfiling(64)
#         print("read %d samples" % len(data))
#         self.processor_thread.push_data(data)
        self.data.append(data)

class SourceLoader(object):
    path_translations = {
            r'C:\Freescale\KSDK_1.0.0-KL43Z' : '/Users/creed/projects/ksdk_releases/KSDK_1.0.0-KL43Z',
            r'E:\projects\KSDK_RELEASES\KSDK_1.0.0-KL43Z' : '/Users/creed/projects/ksdk_releases/KSDK_1.0.0-KL43Z'
        }

    def __init__(self, data, delegate):
        self._data = data
        self._delegate = delegate

    def load_file_for_address(self, addr):
        if self._data.decoder is None:
            return
        lineinfo = self._data.decoder.get_line_for_address(addr)
        if lineinfo is None and isCapstoneAvailable:
            self._load_asm(addr)
            return

        # Translate directory
        dirname=self._translate_path(lineinfo.dirname)
        lineinfo._replace(dirname=dirname)

        path = os.path.join(dirname, lineinfo.filename)
        with open(path, 'r') as f:
            contents = f.read()

        self._delegate.load_source_file(lineinfo, contents, lineinfo.line)

    def _translate_path(self, path):
        if sys.platform != 'win32':
            lowerPath = path.lower()
            for src,dst in self.path_translations.iteritems():
                if lowerPath.startswith(src.lower()):
                    path = dst + path[len(src):]
                    path = path.replace('\\', os.path.sep)
                    path = os.path.normpath(path)
                    break
        return path

    def _load_asm(self, addr):
        (contents, line) = self._get_disasm_for_address(addr)
        if len(contents):
            self._delegate.load_source_file(None, contents, line)
        else:
            self._delegate.load_source_file(None)

    def _get_disasm_for_address(self, addr):
        startAddr = addr - 128
        code = self._load_code_for_addr(startAddr, 256)
        if code is None:
            return ('', 0)
        md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)

        addrLine = 0
        line = 1
        text = ''
        for i in md.disasm(code, startAddr):
            hexBytes = ''
            for b in i.bytes:
                hexBytes += '%02x' % b
            def spacing(s, w):
                return ' ' * (w - len(s))
            text += "0x%08x:  %s%s%s%s%s\n" % (i.address, hexBytes, spacing(hexBytes, 10), i.mnemonic, spacing(i.mnemonic, 8), i.op_str)
            if i.address == addr:
                addrLine = line
            line += 1

        return (text, addrLine)

    def _load_code_for_addr(self, addr, length):
        elf = self._data.decoder.get_elf()
        segments = elf.iter_segments()
        for seg in segments:
            if seg.header['p_type'] != 'PT_LOAD':
                continue
            # Check only filesz, because if memsz is larger then it would be filled with
            # all zeroes, which we don't care about anyway. We want real code.
            filesz = seg.header['p_filesz']
            paddr = seg.header['p_paddr']
            if (addr >= paddr) and (addr < paddr + filesz):
                data = seg.data()
                start = addr - paddr
                end = start + length
                if end > filesz:
                    end = filesz
                data = data[start:end]
                return data
        return None

class ProfileSamplesListCtrl(wx.ListCtrl, ListCtrlAutoWidthMixin):
    def __init__(self, parent, delegate, loader, data):
        wx.ListCtrl.__init__(self, parent, -1, style=wx.LC_REPORT|wx.LC_VIRTUAL|wx.LC_SINGLE_SEL)
        ListCtrlAutoWidthMixin.__init__(self)

        self._delegate = delegate
        self._loader = loader
        self._data = data
#         self._data.add_update_callback(self.data_did_update)

        self.InsertColumn(kTimestampColumn, 'Timestamp', width=100)
        self.InsertColumn(kCurrentColumn, 'mA', width=100)
        self.InsertColumn(kAddressColumn, 'Address', width=120)
        self.InsertColumn(kFunctionColumn, 'Function', width=200)
        self.InsertColumn(kFileColumn, 'Line', width=100)

        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_item_selected)

#         self._needs_update = False
#         self._update_timer = wx.Timer(self)
#         self.Bind(wx.EVT_TIMER, self.on_timer)
#         self._update_timer.Start(100, wx.TIMER_ONE_CONTINUOUS)

    def OnGetItemText(self, index, column):
        return self._data.get_formatted_item(index, column)

    def on_item_selected(self, e):
        addr = self._data.get_address_for_item(e.GetIndex())
        self._loader.load_file_for_address(addr)
        self._delegate.list_item_was_selected(e.GetIndex())

    def on_timer(self, e):
#         print("list timer fired")
        if self._needs_update:
            self.update_data()
#         self._update_timer = None

    def data_did_update(self, data):
        self._needs_update = True
#         if self._update_timer is None: #.IsRunning():
#             self._update_timer = wx.Timer(self)
#             self._update_timer.Start(50, wx.TIMER_ONE_SHOT)
#         wx.CallAfter(self.update_data)

    def update_data(self):
        count = self._data.get_count()
        self.SetItemCount(count)
        self.EnsureVisible(count - 1)

    def set_selected_item(self, index):
        self.deselect_all()
        self.Select(index)
        self.EnsureVisible(index)

    def deselect_all(self):
        while True:
            index = self.GetFirstSelected()
            if index == -1:
                break
            self.Select(index, 0)

class CSourceViewer(wx.stc.StyledTextCtrl):
    def __init__(self, parent, *args, **kwargs):
        wx.stc.StyledTextCtrl.__init__(self, parent, *args, **kwargs)
        self.SetMargins(0, 0)
        self.SetMarginType(0, wx.stc.STC_MARGIN_NUMBER)
        self.SetMarginWidth(0, 20)
        self.SetMarginWidth(1, 0)
        self.SetReadOnly(True)
        self.SetLexer(wx.stc.STC_LEX_CPP)
        self.SetSelectionMode(wx.stc.STC_SEL_LINES)
        self.SetCaretWidth(0)
        self._config_styles()

    def _config_styles(self):
        settings = { 'face' : 'Courier',
                  'size' : 12 }

        styles = {
#                 wx.stc.STC_STYLE_DEFAULT : "face:%(face)s,size:%(size)d",
                wx.stc.STC_STYLE_LINENUMBER : "back:#C0C0C0,face:Courier,size:10",
                wx.stc.STC_STYLE_CONTROLCHAR : "face:%(face)s",
                wx.stc.STC_STYLE_BRACELIGHT : "fore:#FFFFFF,back:#0000FF,bold",
                wx.stc.STC_STYLE_BRACEBAD : "fore:#000000,back:#FF0000,bold",

                wx.stc.STC_C_CHARACTER : 'fore:#808080,face:%(face)s,size:%(size)d',
                wx.stc.STC_C_COMMENT : 'fore:#007F00,face:%(face)s,size:%(size)d',
                wx.stc.STC_C_COMMENTDOC : 'fore:#007F00,face:%(face)s,size:%(size)d',
                wx.stc.STC_C_COMMENTDOCKEYWORD : 'fore:#007F00,face:%(face)s,size:%(size)d',
                wx.stc.STC_C_COMMENTDOCKEYWORDERROR : 'fore:#007F00,face:%(face)s,size:%(size)d',
                wx.stc.STC_C_COMMENTLINE : 'fore:#007F00,face:%(face)s,size:%(size)d',
                wx.stc.STC_C_COMMENTLINEDOC : 'fore:#007F00,face:%(face)s,size:%(size)d',
                wx.stc.STC_C_DEFAULT : 'fore:#808080,face:%(face)s,size:%(size)d',
                wx.stc.STC_C_GLOBALCLASS : 'fore:#0000FF,bold,underline,size:%(size)d',
                wx.stc.STC_C_HASHQUOTEDSTRING : '',
                wx.stc.STC_C_IDENTIFIER : '',
                wx.stc.STC_C_NUMBER : 'fore:#007F7F,size:%(size)d',
                wx.stc.STC_C_OPERATOR : 'bold,size:%(size)d',
                wx.stc.STC_C_PREPROCESSOR : 'fore:#754729',
                wx.stc.STC_C_PREPROCESSORCOMMENT : 'fore:#007F00',
                wx.stc.STC_C_REGEX : '',
                wx.stc.STC_C_STRING : 'fore:#C71711,italic,face:%(face)s,size:%(size)d',
                wx.stc.STC_C_STRINGEOL : 'fore:#000000,face:%(face)s,back:#E0C0E0,eol,size:%(size)d',
                wx.stc.STC_C_STRINGRAW : 'fore:#7F007F,italic,face:%(face)s,size:%(size)d',
                wx.stc.STC_C_TRIPLEVERBATIM : '',
                wx.stc.STC_C_UUID : '',
                wx.stc.STC_C_VERBATIM : '',
                wx.stc.STC_C_WORD : 'fore:#00007F,bold,size:%(size)d',
                wx.stc.STC_C_WORD2 : 'fore:#00007F,bold,size:%(size)d'
            }
        keywords = """alignas alignof and and_eq asm auto bitand bitor bool break case catch char char16_t
            char32_t class compl const constexpr const_cast continue decltype default delete do double
            dynamic_cast else enum explicit export extern false float for friend goto if inline int long mutable
            namespace new noexcept not not_eq nullptr operator or or_eq private protected public register
            reinterpret_cast return short signed sizeof static static_assert static_cast struct switch template
            this thread_local throw true try typedef typeid typename union unsigned using virtual void volatile
            wchar_t while xor xor_eq"""

        # Set keywords.
        self.SetKeyWords(0, keywords)

        # Set all styles to default.
        self.StyleSetSpec(wx.stc.STC_STYLE_DEFAULT, "face:%(face)s,size:%(size)d" % settings)
        self.StyleClearAll()

        for k,v in styles.iteritems():
            if v:
                self.StyleSetSpec(k, v % settings)

        # Hide indicators that show over ifdef'd regions.
        for i in range(3):
            self.IndicatorSetStyle(i, 5)

    def clear(self):
        self.SetReadOnly(False)
        self.SetText('')
        self.SetReadOnly(False)

    def select_line(self, line):
        start = self.PositionFromLine(line-1 if line > 0 else 0)
        end = self.PositionFromLine(line)
#         print("setting sel to %d:%d" % (start, end))
        self.SetSelection(start, end)
        firstVisible = self.GetFirstVisibleLine()
        linesOnScreen = self.LinesOnScreen()
        currentCenter = firstVisible + linesOnScreen / 2
        lineDelta = line - currentCenter
        self.LineScroll(0, lineDelta)

    def load_source_file(self, contents, line=1):
        self.SetReadOnly(False)

        width = self.TextWidth(wx.stc.STC_STYLE_LINENUMBER, str(self.GetLineCount()))
        self.SetMarginWidth(0, width+16)

        self.SetText(contents)
#         self.Colourise(0, self.GetTextLength())
        self.GotoLine(line)
        self.select_line(line)
        self.SetReadOnly(True)

class ProfileWindow(wx.Frame):

    def __init__(self, parent):
        super(ProfileWindow, self).__init__(parent, title='Profiler', size=(1200, 800))

        self.board = None
        self.profile_thread = None
        self._graph_update_timer = wx.Timer(self)
        self._needs_update = False
        self._selected_index = -1
        self._is_connected = False
        self._is_running = False

        self.profile_data = ProfileData()
        self.profile_data.add_update_callback(self.data_did_update)

        self._loader = SourceLoader(self.profile_data, delegate=self)

        self.create_ui()
        self.Center()
        self.Show()
        wx.CallAfter(self.Raise)
        wx.CallAfter(self._refresh_ui)

    def create_ui(self):
        menubar = wx.MenuBar()
        fileMenu = wx.Menu()
        fitem = fileMenu.Append(wx.ID_EXIT, '&Quit', 'Quit application')
        fitem2 = fileMenu.Append(2, u'Select ELF file…\tCTRL-O', 'Choose ELF file to use')
        menubar.Append(fileMenu, '&File')
        self.SetMenuBar(menubar)

        self.Bind(wx.EVT_MENU, self.on_quit, fitem)
        self.Bind(wx.EVT_MENU, self.on_choose_elf, fitem2)

        # Create status panel
        self.status_panel = wx.Panel(self)
        panelSizer = wx.BoxSizer(wx.HORIZONTAL)

        self.status_text = wx.StaticText(self.status_panel, pos=(10,10), size=(300,30), style=wx.ALIGN_LEFT)
        self.status_text.SetLabel("Not connected")
        panelSizer.Add(self.status_text, proportion=1, flag=wx.EXPAND|wx.ALIGN_BOTTOM|wx.LEFT, border=10)

        self.elf_text = wx.StaticText(self.status_panel, pos=(10,10), size=(300,30), style=wx.ALIGN_RIGHT|wx.ST_NO_AUTORESIZE)
        self.elf_text.SetLabel("No file selected")
        panelSizer.Add(self.elf_text, proportion=1, flag=wx.EXPAND|wx.ALIGN_BOTTOM|wx.RIGHT, border=10)

        self.connect_button = wx.Button(self.status_panel, label='Connect')
        self.connect_button.Bind(wx.EVT_BUTTON, self.on_connect)
        panelSizer.Add(self.connect_button, proportion=0, flag=wx.ALIGN_RIGHT|wx.RIGHT, border=10)

        self.start_stop_button = wx.Button(self.status_panel, label='Start')
        self.start_stop_button.Bind(wx.EVT_BUTTON, self.on_start_stop)
        self.start_stop_button.Disable()
        panelSizer.Add(self.start_stop_button, proportion=0, flag=wx.ALIGN_RIGHT|wx.RIGHT, border=10)

        self.clear_button = wx.Button(self.status_panel, label='Clear')
        self.clear_button.Bind(wx.EVT_BUTTON, self.on_clear)
        panelSizer.Add(self.clear_button, proportion=0, flag=wx.ALIGN_RIGHT|wx.RIGHT, border=10)

        self.status_panel.SetSizer(panelSizer)

        vsizer = wx.BoxSizer(wx.VERTICAL)
        vsizer.Add(self.status_panel, 0, flag=wx.TOP|wx.EXPAND, border=10)

        hsplitter = wx.SplitterWindow(self, style=wx.SP_3D|wx.SP_LIVE_UPDATE)
        hsplitter.SetMinimumPaneSize(200)
        hsplitter.SetSashGravity(1.0)

        vsplitter = wx.SplitterWindow(hsplitter, style=wx.SP_3D|wx.SP_LIVE_UPDATE)
        vsplitter.SetMinimumPaneSize(250)
        vsplitter.SetSashGravity(1.0)

        self.graph = plot.PlotCanvas(vsplitter)
        self.graph.SetPointLabelFunc(self._draw_point_label)
#         self.graph.SetEnableHiRes(True)
        self.graph.SetEnablePointLabel(True)
        self.graph.SetShowScrollbars(True)
        self.graph.SetEnableZoom(True)
#         self.graph.SetEnableDrag(True)
        self.graph.canvas.Bind(wx.EVT_LEFT_DOWN, self.on_plot_mouse_left_down)
        self.graph.canvas.Bind(wx.EVT_MOTION, self.on_plot_motion)
        self._config_graph()

        self.list = ProfileSamplesListCtrl(vsplitter, self, self._loader, self.profile_data)

        vsplitter.SplitHorizontally(self.graph, self.list, 500)

        self.code = CSourceViewer(hsplitter)

        hsplitter.SplitVertically(vsplitter, self.code, -500)

        vsizer.Add(hsplitter, 1, wx.EXPAND|wx.ALL)

        self.SetSizer(vsizer)

        self.status_bar = self.CreateStatusBar()
        self.status_bar.SetStatusText('Stopped')

#         self._graph_update_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer)
        self.Bind(wx.EVT_CLOSE, self.on_close)

        self.data_did_update(self.profile_data)

    def on_quit(self, e):
        self.Close()

    def on_choose_elf(self, e):
        self.elf_path = wx.FileSelector(parent=self)
        if self.elf_path is not None:
            self.elf_text.SetLabel(u'Loading…')
            self.profile_data.set_elf_file(self.elf_path, self._elf_did_load)

    def _elf_did_load(self):
        wx.CallAfter(self._update_elf)

    def _update_elf(self):
        self.elf_text.SetLabel(os.path.basename(self.elf_path))
        self.list.update_data()

    def on_connect(self, e):
        if self._is_connected:
            self._is_connected = False
            try:
                if self._is_running:
                    self.on_start_stop()
                self.board.uninit()
            except Excetion as e:
                print("Got exception while disconnecting:", e)
            self.board = None
            self.connect_button.SetLabel('Connect')
            self.status_text.SetLabel('Not connected')
            self.start_stop_button.SetLabel('Start')
            self.start_stop_button.Disable()
        else:
            self.board = pyOCD.board.MbedBoard.chooseBoard(blocking=False, return_first=True)
            if self.board is not None:
                self._is_connected = True
                pyOCD.transport.cmsis_dap_core.dapSWJClock(self.board.interface, 8000000)
                self.board.target.resume()

                self.connect_button.SetLabel('Disconnect')
                self.status_text.SetLabel('Connected to ' + self.board.target.part_number)
                self.status_panel.GetSizer().Layout()
                self.start_stop_button.SetLabel('Start')
                self.start_stop_button.Enable()

    def on_start_stop(self, e):
        if not self._is_connected:
            return

        if not self._is_running:
            self.profile_data.clear()
            self.profile_thread = ProfilerThread(self.board, self.profile_data)
            self.profile_thread.start()
#             if not self.profile_thread.is_running():
#                 self.profile_thread.stop()
#                 self.profile_thread = None
#                 self.status_bar.SetStatusText('Failed to start')
#             else:
            self._update_status_text()
            self.start_stop_button.SetLabel('Stop')
            self._graph_update_timer.Start(100, wx.TIMER_CONTINUOUS)
            self._is_running = True
        else:
            self._graph_update_timer.Stop()
            self.profile_thread.stop()
            self.profile_thread = None
            self._update_status_text()
            self.start_stop_button.SetLabel('Start')
            self.graph.SetShowScrollbars(True)
            self._is_running = False

    def on_clear(self, e):
        self.profile_data.clear()
        self._refresh_ui()

    def on_plot_mouse_left_down(self, e):
        dlst = self.graph.GetClosestPoint(self.graph._getXY(e), pointScaled=True)
        if len(dlst):    #returns [] if none
            curveNum, legend, index, pointXY, scaledXY, distance = dlst
            self._selected_index = self.profile_data.graph_index_to_data_index(index)
            self.list.set_selected_item(self._selected_index)
            self._refresh_graph()
        e.Skip()

    def on_plot_motion(self, e):
        #show closest point (when enbled)
        if self.profile_data.get_count():
            #make up dict with info for the pointLabel
            #I've decided to mark the closest point on the closest curve
            dlst = self.graph.GetClosestPoint(self.graph._getXY(e), pointScaled=True)
            if len(dlst):    #returns [] if none
                curveNum, legend, pIndex, pointXY, scaledXY, distance = dlst
                #make up dictionary to pass to my user function (see DrawPointLabel)
                mDataDict= {"curveNum":curveNum, "legend":legend, "pIndex":pIndex,\
                            "pointXY":pointXY, "scaledXY":scaledXY}
                #pass dict to update the pointLabel
                self.graph.UpdatePointLabel(mDataDict)
        e.Skip()           #go to next handler

    def on_timer(self, e):
        if self._needs_update:
            self._refresh_ui()

    def on_close(self, e):
        if self._is_connected:
            self.on_connect(None)
        wx.Exit()

    def data_did_update(self, data):
        self._needs_update = True

    def list_item_was_selected(self, index):
        self._selected_index = index
        self._refresh_graph()

    def _refresh_ui(self):
        self._needs_update = False
        self._update_status_text()
#         with ElapsedTimer('list update'):
        self.list.update_data()
        self._refresh_graph()

    def _refresh_graph(self):
#         with ElapsedTimer('build graph'):
        graphBuilder = ProfileGraphBuilder(self.profile_data, width=2000, selected=self._selected_index)
#         with ElapsedTimer('draw graph'):
        self.graph.Draw(graphBuilder.get_graphics(), xAxis=graphBuilder.get_xaxis(), yAxis=(0,10))

    def _draw_point_label(self, dc, mDataDict):
        index = -1
        try:
            dc.SetPen(wx.Pen(wx.BLACK))
            dc.SetBrush(wx.Brush( wx.BLACK, wx.SOLID ) )

            sx, sy = mDataDict["scaledXY"] #scaled x,y of closest point
#             dc.DrawRectangle( sx-2,sy-2, 2, 2)
            dc.DrawCircle(sx, sy, 2)

            index = self.profile_data.graph_index_to_data_index(mDataDict["pIndex"])

            ts = self.profile_data.get_formatted_item(index, kTimestampColumn)
            mA = self.profile_data.get_formatted_item(index, kCurrentColumn)
            addr = self.profile_data.get_formatted_item(index, kAddressColumn)
            s = "%s: %s %s" % (ts, mA, addr)
            dc.DrawText(s, sx-5 , sy+1)
        except IndexError:
            print("invalid index:", index)

    def _update_status_text(self):
        self.SetStatusText("%d samples" % self.profile_data.get_count())

    def _config_graph(self):
        self.graph.SetXSpec('auto')
        self.graph.SetYSpec('auto')

    def load_source_file(self, info, contents='', line=1):
        if info is not None:
            print("loading file %s, %d bytes" % (info.filename, len(contents)))
        self.code.load_source_file(contents, line)

class ProfileApp(wx.App):
    def __init__(self):
        wx.App.__init__(self)

        self.win = ProfileWindow(None)

if __name__ == '__main__':
    import wx.py.PyWrap
    app = ProfileApp()
    wx.py.PyWrap.wrap(app)
#     ProfileWindow(None)
    #plot.TestFrame(None, 1, "hi")
#     app.MainLoop()
