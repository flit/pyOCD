---
title: CMSIS-DAP internals
---

This article documents some of the internal structure of the CMSIS-DAP protocol engine.

There are two classes used to manage requests and responses:

- `_Command` optimally merges multiple read/write requests into a DAP_Transfer or DAP_TransferBlock command, up to the probe's maximum packet size.
- `_Transfer` tracks the expected response data size of higher level transfers and provides a place to save the response data when it is received.

Instances of these classes are tracked as:

- The current, unsent `_Command`. New requests are merged into this object as long as they will fit. (See below.)
- Queue of `_Command` objects for which the request has been sent but the response not yet received.
- Queue of `_Transfer` objects.

Any one transfer from the higher levels, via the `DAPAccessCMSISDAP.reg_{write,read}()` or `DAPAccessCMSISDAP.reg_{write,read}_repeat()` methods, will result in a single `_Transfer` object, but possibly multiple `_Command` objects, and requests being sent. Multiple commands are used mostly for larger block transfers, such as memory r/w through a MEM-AP; these handled via the `.reg_{write,read}_repeat()` methods of `DebugProbe`.

In the discussion below, a "request" is the DAP + CMSIS-DAP transfer request byte. This contains the following DAP request information:
- Standard ADI transfer attributes
    - APnDP
    - RnW
    - A[3:2]
- CMSIS-DAP specific request attributes
    - Value match
    - Match mask
    - Timestamp flag (note that timestamp requests aren’t supported by pyOCD yet)

See the [DAP_Transfer](https://arm-software.github.io/CMSIS_5/develop/DAP/html/group__DAP__Transfer.html) documentation for full details.

Merging of new transfers into the current (unsent) command is attempted in all cases. The current `_Command` will only be sent in case of:

1. An explicit flush.
2. A new request not fitting into or being compatible with the current `_Command`.
3. Deferred transfers being disabled; this causes a flush at the end of `DAPAccessCMSISDAP._write()`.

There are a number of rules about what requests can be appended to a `_Command`:

1. Must have same DAP index. Currently this is always 0 for pyOCD, and the reference CMSIS-DAP code currently just ignores it, anyway.
2. Block transfers (DAP_TransferBlock) must use the same request.
3. Must be room for the additional request. While this is obvious, there’s more to it:
    1. Both the request and response packet sizes are tracked; a new request overflowing either size will trigger a send.
    2. Size tracking covers the case where a command has been filled as a block transfer (self._block_request is set), the new request is not the same as the block request, and there is not enough room to convert the block transfer back to a non-block transfer

It is `DAPAccessCMSISDAP._write()` that contains the logic to check if new requests can be merged, send a full command, and create new `_Command` instances as needed.

Once a `_Command` is full, it is sent immediately by `DAPAccessCMSISDAP._write()` calling `DAPAccessCMSISDAP._send_packet()`. `DAPAccessCMSISDAP._send_packet()` ensures that no more command packets are outstanding than the number specified by the  probe in its "max packet count" DAP_Info response.


Every transfer (anything that calls `DAPAccessCMSISDAP._write()`) results in a `_Transfer` object being created and appended to an ordered list of outstanding transfers. For read transfers, the `_Transfer` object is returned to the caller.

`DAPAccessCMSISDAP._read_packet()` is invoked in these two cases:

1. When either `_Transfer.get_result()` or `DAPAccessCMSISDAP.flush()` are called.
2. When a new request needs to be sent and there are as many outstanding requests than the probe supports.

The `._read_packet()` method reads a single command response via the `Interface` object (the USB interface) and asks the relevant `_Command` to decode it. A temporary buffer is used to store decoded response data. Once the data in the temporary buffer is large enough to complete the next transfer, it is attached to the `_Transfer` object.


