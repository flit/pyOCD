---
title: GDB setup
---

Most users will want to set up the GNU GDB debugger in order to use pyOCD for debugging applications. Either
the command-line GDB or a full IDE can be used.


Standalone GDB server
---------------------

After you install pyOCD via pip or setup.py, you will be able to execute the following in order to
start a GDB server powered by pyOCD:

```
$ pyocd gdbserver
```

You can get additional help by running ``pyocd gdbserver --help``.

Example command line GDB session showing how to connect to a running `pyocd gdbserver` and load
firmware:

```
$ arm-none-eabi-gdb application.elf

<gdb> target remote localhost:3333
<gdb> load
<gdb> monitor reset
```

The `pyocd gdbserver` subcommand is also usable as a (mostly) drop in place replacement for OpenOCD in
existing setups. The primary difference is the set of gdb monitor commands.

The [gdbserver documentation]({% link _docs/gdbserver.md %}) has more information on the features of the gdbserver.


Recommended GDB and IDE setup
-----------------------------

The recommended toolchain for embedded Arm Cortex-M development is [GNU Arm
Embedded](https://developer.arm.com/downloads/-/gnu-rm) (GNU-RM),
provided by Arm. GDB is included with this toolchain.

Note that the version of GDB included with the new, combined Arm GNU Toolchain as of version 11.2-2022.02
_will not_ work with pyOCD. This is because it is currently built without the required support for the XML
target descriptions that pyOCD sends to GDB. Versions later than 11.2-2022.02 may have this bug fixed.

For [Visual Studio Code](https://code.visualstudio.com), the
[cortex-debug](https://marketplace.visualstudio.com/items?itemName=marus25.cortex-debug) plugin is available
that supports pyOCD.

The GDB server also works well with [Eclipse Embedded CDT](https://projects.eclipse.org/projects/iot.embed-cdt),
previously known as [GNU MCU/ARM Eclipse](https://gnu-mcu-eclipse.github.io/). It fully supports pyOCD with
an included pyOCD debugging plugin.

To view peripheral register values, the built-in peripheral views provided by cortex-debug and Eclipse Embedded CDT can be used. However, see the note below about accessing device memory from gdb.


Accessing device memory
-----------------------

For several reasons, neither pyOCD's built-in target types nor those defined in Open-CMSIS-Pack Device Family Packs by silicon vendors typically include device (peripheral) regions in the memory map. And, by default, gdb restricts access to the memory map supplied it to. This results in gdb returning errors for attemtped accesses to device memory.

The standard solution for this is to issue the `set mem inaccessible-by-default no` command to gdb, so it ignores the supplied memory map and allows all accesses to be sent to pyOCD, and on to the target itself. Then the target itself will return a fault for truly invalid accesses. (Note that some devices, such as the Nordic Semiconductor nRF series, do not fault invalid memory transfers and instead ignore writes and return 0.)

If device memory regions must be defined for some reason, they can be added with a [user script]({% link _docs/user_scripts.md %}).
