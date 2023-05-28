---
title: Basic concepts
---

This guide covers the basic requirements for using pyOCD.


For subcommands that connect to a device, pyOCD needs a few bits of information to do its job:

- Target type — _what_ kind of device
- Debug probe — _how_ to control the device, and implicitly _which_ device



## Target and target type

The _target type_ determines _what_ type of device is being debugged. In other words, the device family and
part number. _Which_ specific device is being debugged is called the _target_. Sometimes the term _target_ is used to mean _target type_; the context should make it clear which is intended.

Target types combine a memory map, flash programming algorithms, special debug control logic, and any other information that distinguishes how that device is controlled.

There are two sources of target type definitions:

1. Built-in to pyOCD
2. CMSIS Device Family Packs (DFPs)

DFPs are available for nearly all Cortex-M based MCUs. They can be easily searched and installed using the `pyocd pack` subcommand, as described below.


## Debug probe

The interface used to talk with and control the target is called the _debug probe_, or just _probe_. It's basically a protocol translator. Typically, a debug probe is connected to a host computer using USB or Ethernet. The other side of the probe is connected to the target using a _wire protocol_ such as SWD or JTAG.

Because a debug probe is connected directly to the target, selecting a debug probe also selects the target.

There are two major kinds of debug probe, in terms of how they are connected to the target:

- On-board debug probes: Connected to the target using PCB traces, usually on a development kit or board. On some boards, the on-board probe can configured to be work as a standalone probe and connected to another board with a cable.
- Standalone debug probes: A cable connects the probe to the PCB on which the target device resides. This makes standalone probes the right choice for debugging custom boards for projects where you don't want the added expense and area of an on-board probe.

For pyOCD, the most important distintion between on-board and standalone debug probes is that certain on-board probes can indicate the target type to which they are connected.

There are also many host interface protocols used to communicate with different kinds and makes of debug probes. PyOCD uses plugins to enable access to these diverse array of probes and protocols. See the complete [debug probe documentation]({% link _docs/debug_probes.md %}) for more information about debug probe types and plugins.


## Selecting a debug probe

Every debug probe has a unique identifier. PyOCD uses the unique ID to select a debug probe for use, and therefore the target to debug.

There are a few methods to select the debug probe.

1. If only one probe is connected to the host, it will be used automatically.
2. If multiple probes are connected but none is selected on the command line, a prompt will be displayed on the console asking to select one.
3. Use the `-u UID` / `--uid=UID` / `--probe=UID` command line argument to select a probe.
4. When using pyOCD's Python API, pass the `unique_id` parameter to one of the `ConnectHelper` methods.

The UID parameter is case insensitive and unambiguous partial matches are allowed.

Note: the debug probe cannot currently be selected using a config file.


## Specifying the target type

Each target type has a name, the _target type name_. This is often the full part number, though for built-in target types it can be a shortened version. The target type name is always displayed in lower case but is case-insensitive. Examples are `k64f`, `stm32l475xg`, `nrf5340_xxaa`, `k32l3a60vpj1a`, and so on.

As mentioned earlier, many on-board debug probes can help pyOCD select the target type automatically. For standalone probes, the target type must be set manually.

To specify the target type, use the `-t NAME` / `--target=NAME` command line argument. Alternatively, the `target_override` session option can be set in a config file or script.


## Check and install target support

The `pyocd list` command is used to display available debug probes along with their unique ID and other information. If the debug probe reports it, this will include the default target type for the board. Using `pyocd list` is a good way to quickly check if the target type must be manually set and/or installed.

This is example output from `pyocd list` with a couple probes connected:

      #   Probe/Board                       Unique ID                                          Target
    --------------------------------------------------------------------------------------------------------------------
      0   Arm DAPLink CMSIS-DAP             02400b0129164e4500440012706e0007f301000097969900   ✔︎ k64f
          NXP                               FRDM-K64F

      1   STLINK-V3                         002500074741500420383733                           ✖︎ stm32u585aiix
          B-U585I-IOT02A

In this case, both debug probes are on-board and report the default target type for their board (the board name is shown in the second row of each listed probe). The "Target" column reports the target type names for each probe, and whether that target type is installed with a check or X mark. Here, the `k64f` target type is installed (because it's built-in), while the `stm32u585aiix` is not installed. By definition, any target type not installed is supported through a DFP.

If the target type support for your board is not installed, the `pyocd pack` subcommand can quickly install it. The `find` and `install` subcommands take a part number argument, and list or install DFPs that contain matching devices.

- To search for a target type: `pyocd pack find PART-NUMBER`
- To install a target type: `pyocd pack install PART-NUMBER`

The part number argument is case insensitive, and partial names are accepted.

The first time either subcommand is run, a database of CMSIS Packs will be downloaded. If a part number being searched for isn't found and it has been a while since the database was updated, it can be updated by running `pyocd pack update`.


## Session options

For configuration, pyOCD uses _session options_. They are called this because they can be different for each debug session (duration during which a debug probe is connected), but are consistent within such a session.

Most common session options have dedicated command line arguments. Options can be set by name with the `-O OPTION[=VALUE]`command line argument, in config files, as well as through scripting with the Python API.

See the [session option reference]({% link _docs/options.md %}) for the set of available options.


## Configuration files

Session options can conveniently be placed into [YAML](https://yaml.org) config files which pyOCD can automatically load. Config files


