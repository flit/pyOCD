---
title: Command line overview
---

PyOCD's main user interface is the `pyocd` command line tool. It provides a number of subcommands for performing different actions.


### Commands

###### Setup

<table class="no-alternating-rows">
<tr><td width="20%"> <code>pack</code></td>     <td> Install target support via Open-CMSIS-Pack Device Family Packs</td></tr>
<tr><td width="20%"> <code>list</code></td>     <td> List connected probes, available targets, and other features</td></tr>
</table>

###### Development

<table class="no-alternating-rows">
<tr><td width="20%"> <code>gdbserver</code> </td><td> GDB remote server </td></tr>
<tr><td width="20%"> <code>load</code>      </td><td> Load code/data images to target memory </td></tr>
<tr><td width="20%"> <code>rcode</code>     </td><td> SEGGER RTT viewer and logger </td></tr>
</table>

###### Target control

<table class="no-alternating-rows">
<tr><td width="20%"> <code>commander</code> </td><td> pyOCD command execution and interactive REPL </td></tr>
<tr><td width="20%"> <code>reset</code>     </td><td> Reset a target </td></tr>
</table>

###### Miscellaneous

<table class="no-alternating-rows">
<tr><td width="20%"> <code>json</code>      </td><td> Extract data as JSON </td></tr>
<tr><td width="20%"> <code>server</code>    </td><td> Run the pyOCD remote probe protocol server </td></tr>
</table>



### Common arguments

Subcommands that connect to a target share a number of command line arguments for configuration and control of the target connection.

#### Connection

Arguments for controlling the debug probe, target type, and how pyOCD connects to the target.

###### `-u ID`, `--uid=ID`, `--probe=ID`
Select the debug probe used to control the target. See the [debug probe]({% link _docs/debug_probes.md %}) documentation for more details. For USB probes, the argument value only needs to be a unique subset of available probe IDs (those shown by `pyocd list`), and is not case sensitive.

To limit selection of probe types, the argument value can be prefixed with the name of a debug probe plugin (run `pyocd list --plugins` to see a plugin list) and a colon (a lot like a URL scheme). For example, `--probe=cmsisdap:L02A` selects a CMSIS-DAP probe whose unique ID contains "L02A".

###### `-t TYPE`, `--target=TYPE`
Specify the target type name. Required if either the debug probe doesn't tell pyOCD the target type, or the probe's default target type needs to be overridden (for instance if using an on-board probe to connect to a custom board).

If the probe doesn't report a default target type, the `cortex_m` target type will be used as the default. This makes it impossible to program flash, and pyOCD will fail to connect to certain device families. Because of the limitations of `cortex_m`, a warning is logged unless the `--target` argument is used to explicitly select `cortex_m` or the `warning.cortex_m_default` session option is disabled.

###### `-f HZ`, `--frequency=HZ`
Set the SWD/JTAG frequency used by the debug probe in Hertz. \
Accepts a float or int with optional, case-insensitive `K` / `M` suffix and optional `Hz`. Examples: `-f 1000`, `--frequency=2.5khz`, `-f10M`.

###### `-M MODE`, `--connect=MODE`
The connection mode, one of the following.

- `halt`: *The default mode if not specified.* Connects to the target and immediately halts all cores without performing any resets.
- `pre-reset`: Reset the target using the nRESET pin prior to connecting. Otherwise the same as `halt`.
- `under-reset`: Holds the nRESET pin asserted during the connection sequence, until cores are successfully halted (unless they are inaccessible, eg held in reset by internal reset logic).
- `attach`: Leave cores running during connect. This is useful for reading data from code running on the MCU without interrupting its behaviour, eg SWO or RTT. No resets are performed since this would interrupt running code.

###### `-W`, `--no-wait`
If no debug probes are connected, exit immediately instead of waiting until one becomes available.



#### Configuration

Arguments for configuring pyOCD. See the [configuration]({% link _docs/configuration.md %}) documentation for a detailed description of how to configure pyOCD.

###### `-j PATH`, `--project=PATH`, `--dir=PATH`
Set the project directory. Defaults to the directory where pyocd was run.

###### `--config=PATH`
Specify YAML configuration file. Defaults to` pyocd.yaml` or `.pyocd.yaml`, or either name with a `.yml` extension, in the project directory.

###### `--no-config`
Do not use a configuration file.

###### `--script=PATH`
Use the specified user script. Defaults to `pyocd_user.py` or `.pyocd_user.py` in the project directory.

###### `-O OPTION=VALUE`
Set the named session option.

For boolean session options, the value can be excluded and the option will be set to true, or the option name can be prefixed with `no-` to disable the option.

###### `--pack=PATH`
Path to the .pack file for a CMSIS Device Family Pack.


