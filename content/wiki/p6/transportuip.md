---
title: TRANSPORTUIP — microcode calls through a link register
updated: 2026-09-17
---

`TRANSPORTUIP` appears to
materialize an explicit microcode address into a temporary register. A later
indirect microjump uses that register to return from a helper. This supports a
**link-register calling convention**; it does not establish an implicit call stack.

## A call to the I/O permission helper

The REP INS candidate saves its continuation in `TMP0`, then jumps to the shared
I/O permission-check candidate at `33E5`. Selected operations are shown below;
intervening setup and checks are omitted. Microaddresses are hexadecimal, and
`#n` denotes a signed literal in decimal.

```asm
2618      TMP0        TRANSPORTUIP       261D
          ; Count and control setup omitted.
261C                  U_JMP.NT           33E5
261D      REG.37      AND.DSZ32          REG.37, #-240
          ; REP INS continues here.

33E5      TMP3        MOVE.DSZ32         0, 0
          ; Permission checks and return-path bookkeeping omitted.
3402                  U_JMP_INDIR.NT     0, TMP0

          ; Separate fault path:
3404      TMP3        MOVE.DSZ32         #193, #193
3405      TMP4        UOP.120            #13, #13
3406  E               SIGEVENT           TMP4, TMP3
```

The normal control flow is:

```text
TMP0 = microaddress(261D)
goto 33E5
    ... helper preserves TMP0 ...
    goto TMP0
resume at 261D
```

Three details distinguish this from an automatic call/return mechanism:

- `261D` is explicitly encoded. It is not the instruction immediately after
  `TRANSPORTUIP`, which is at `2619`.
- `TRANSPORTUIP` does not jump. The separate `U_JMP.NT` at `261C` enters the helper.
- The normal return is the indirect jump at `3402`. The **E** bit at `3406`
  belongs to the fault-event path; it is not the return mechanism here.

Another example uses `TMP2`: `12B8` materializes `1166`, `12BC` jumps to `1271`,
and the shared path through `37DD` returns via `U_JMP_INDIR.NT (0, TMP2)`.
Thus the observed return register is chosen by the microcode, not one fixed
architectural link register.

Related: [P6 ROMs and PLAs](roms.md) · [Wiki home](../index.md)
