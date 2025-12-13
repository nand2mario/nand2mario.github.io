---
title: "z8086: Rebuilding the 8086 from Original Microcode"
date: 2025-12-13T17:25:20+08:00
draft: false
sidebar: false
comment: true
author: nand2mario
---

After [486Tang](https://nand2mario.github.io/posts/2025/486tang_486_on_a_credit_card_size_fpga_board/), I wanted to go back to where x86 started. The result is [**z8086**](https://github.com/nand2mario/z8086): a clean‑room 8086/8088 core that runs the **original Intel microcode**. Instead of hand‑coding hundreds of instructions, the core loads the recovered 512x21 ROM and recreates the micro‑architecture the ROM expects.

z8086 is compact and FPGA‑friendly: it runs on a single clock domain, avoids vendor-specific primitives, and offers a simple external bus interface. Version 0.1 is about 2000 lines of SystemVerilog, and on a Gowin GW5A device, it uses around 2500 LUTs with a maximum clock speed of 60 MHz. The core passes all ISA test vectors, boots small programs, and can directly control peripherals like an SPI display. While it doesn’t boot DOS yet, it’s getting close.  

<!--more-->

---

## Why another x86?

The 8086 is where the x86 story began. If you want to understand why x86 feels like x86 — segmented addressing, ModR/M, the prefetch queue, the oddball string instructions — this is the chip to study.

Also, reverse-engineering of the 8086 has reached a surprisingly level of maturity. We now have Ken Shirriff’s massive [8086 blog series](https://www.righto.com/search/label/8086) and Andrew Jenner's [disassembled microcode](https://www.righto.com/2023/04/8086-microcode-string-operations.html). Combined with the original [8086 patent](https://patents.google.com/patent/US4449184A/en), these resources make it possible to rebuild a *faithful* core instead of a functional approximation.

My goals were simple:

- **Faithful where it counts.** Accurately replicate the microarchitectural behavior of the original 8086 wherever it matters most.
- **Designed to be explorable and educational.** The code is thoroughly commented to make it clear and easy to understand. Aims to be a good teaching resource.
- **FPGA-friendly and practical.** z8086 is built to be an effective, useful CPU IP core for real FPGA projects.

---

## Re‑creating the 8086

Here’s the high‑level view:

![z8086 block diagram](z8086.svg)

At a bird’s‑eye level the pipeline is:

**Prefetch queue → Loader (FC/SC) → Microcode sequencer → EU/BIU datapath**

This is like the original chip’s split. The **BIU** (bus interface unit) runs ahead, fetching bytes into a 6‑byte queue whenever the bus is idle. The **EU** (execution unit) consumes bytes from that queue, decodes them, and drives the microcode engine. When the EU needs memory, it issues a Type‑6 micro‑op; the BIU yields the bus and prefetch pauses. That overlap is why the 8086 feels “pipelined” despite being a late‑70s design.

Microcode is the glue here. Each 21‑bit micro‑instruction encodes a **move** (5‑bit source → 5‑bit destination on an internal bus) plus an **action** (ALU op, short/long jump, bookkeeping, or a bus cycle). The sequencer advances through `{AR, CR}` addresses until the microcode asserts “run next instruction.”

Some key pieces:

- **Microcode engine.** The sequencer keeps `{AR, CR}` (plus `SR` for calls), fetches 21‑bit words from `ucode.hex`, and executes them as a tight move→action loop. `ROME` marks active execution. When microcode wants a queue byte (`LOC_Q`) but the queue is empty, or when an EU bus cycle is in flight, a `stall` signal freezes `CR` so the ROM sees exactly the timing it expects.

- **Translation + group decode.** The original 8086 uses ROMs to (1) classify opcodes into ~15 “group” signals (“has ModR/M,” “prefix,” “uses w‑bit,” “grp3/4/5,” etc.), and (2) map `{opcode, ModR/M}` to microcode entry points for effective‑address and control‑flow routines. z8086 implements these as combinational replicas (`group_decode()` and `translate()`), derived from the dumped ROM truth tables. This is what lets the recovered microcode drop straight in without being rewritten.

- **Bus + unaligned access.** Externally you get `rd/wr/io/word/ready` with aligned cycles, so FPGA memory is easy to hook up. Internally the EU still issues Type‑6 bus micro‑ops with the right segment defaults and overrides. If a word access lands on an odd address, the bus FSM automatically splits it into two byte cycles (`BUS_UNALIGNED`), so software sees real 8086 semantics while the outside world stays aligned.

- **ALU + flags.** The ALU is implemented as a classic 16×1‑bit slice, controlled by signals modeled after Intel’s original logic. The initial ALU design used Verilog primitives, but this updated bit‑slice version is both smaller and faster, closely replicating the behavior of the original chip’s ALU.

One concrete example: for a ModR/M instruction like `ADD AX, [BX+SI+4]`, the loader’s `FC` grabs the opcode, `SC` grabs the ModR/M byte, `translate()` jumps into the right effective‑address micro‑routine, the EU reads the operand through a Type‑6 bus cycle into `OPR`, the ALU updates `SIGMA` and flags, and a final Type‑6 writeback happens only if the instruction targets memory.

---

## Interesting discoveries

### Microcode is super efficient

The 8086 shipped with ~29K transistors and still delivered a very rich CISC ISA: segmented addressing, ModR/M base+index+disp modes, and weirdly specialized instructions like `DAA` and `XLAT`. The trick was microcode. A small internal datapath plus ROM sequencing let Intel implement a huge instruction surface area without exploding logic.

The contrast with other CPUs is striking. The 6502 (~4.5K transistors) and Z80 (~8.5K) are elegant, mostly hardwired, and highly minimalist designs. In comparison, the 8086 features a much wider datapath, significantly more instructions and features, yet manages to do so with less than four times the transistor count of the Z80. The 68000 (~68K transistors) takes a different approach, using far more silicon for its fully hardwired CISC design. Remarkably, the 8086 achieves a similar feature set with less than half the transistor count of the 68000. This efficiency carries over to z8086: the core fits into just 2,500 LUT4s — dramatically smaller than ao486, which is about ten times larger.

### The patent’s FC/SC formulas are wrong (or at least incomplete)

Interestingly, the patent’s explanation of FC and SC signal generation turns out to be inconsistent. The formulas it provides are:

```
FC = [(00) + (10)(NXT + RNI)]·MT
SC = [(01) + (11)](2BR·MT)
```

Here, "MT" refers to "a signal generated by Q control circuitry indicating that the queue is empty...". In reality, however, the correct logic should be "**not MT**"" rather than MT, contrary to the documentation. Testing and implementation confirm that this change results in the expected loader behavior.

### The “8086 interrupt bug" 

The original 1978 8086 had an interrupt-related bug: If an interrupt occurs immediately after a `MOV SS,xxx` or `POP SS` instruction, the CPU may push data to an incorrect stack address, corrupting memory. The problem arises because both the Stack Segment (SS) and Stack Pointer (SP) must be updated to ensure correct stack operations. If an interrupt arrives between these updates, the CPU could save flags/IP/CS to the wrong location. Intel later resolved this by automatically disabling interrupts for one instruction following operations like `POP SS`.

z8086 faithfully reproduces this edge case using a `delay_interrupt` register. This register is set whenever one of three events occurs: when `SC` decodes a **prefix** (`g_prefix`), a **stack segment load** (`POP SS`), or a **segment register move** (`MOV sr, r/m`, detected by `g_seg_reg_bits`). This mechanism disables interrupt handling for exactly one instruction, matching the original 8086's behavior.

### The prefetch queue bus is 8-bit

The prefetch queue is a 6-byte buffer that continuously feeds the execution engine. Its output, called the "Q Bus," is an 8-bit bus delivering the next instruction byte. Notably, while the 8086 is architecturally a 16-bit CPU, it fetches instruction bytes one at a time—consuming at most a single byte per cycle. This design ultimately limits performance, a bottleneck that later Intel CPUs overcome; for instance, the 386 features a 32-bit wide Q bus.

Working on ao486 for 486Tang underscored just how crucial the prefetch queue is to overall performance and Fmax. The intricate x86 instruction set makes optimizing the queue challenging. Balancing width, depth, and flexibility in its design truly tests the designer’s skill.

---

## Reflections and next steps

Overall, this project has been incredibly fun — like piecing together a giant puzzle. It involves gathering information from many sources, making educated guesses about the original design, and testing those theories until everything clicks into place.

Getting code to work is the definitive proof of truly understanding a system. The fact that z8086 functions as intended demonstrates that the community now possesses deep, practical insight into the original x86 chip.

Intel packed an impressive array of features into the 8086. Some attribute this to it being designed by a [software developer](https://thechipletter.substack.com/p/trillion-dollar-stopgap-the-intel). While many of these features have become less relevant over time — and some of the 8086’s success was undoubtedly lucky, such as being chosen for the IBM PC — the developer-friendly design played a big role in kickstarting the x86 ecosystem.

This release is an early preview and comes with several limitations: it is not yet cycle accurate, the interrupt circuitry is still under-tested, the original 8086 bus cycles are not fully replicated, and it has not yet been used to run large programs.

Here are some directions I plan to work on:

- More extensive testing on FPGA boards
- Booting DOS
- Compiling to WebAssembly for interactive 8086 visualization in the browser?

[z8086](https://github.com/nand2mario/z8086) should work on most FPGAs, with sample projects provided for DE10-Nano, Xilinx Artix7 and Tang Console 60K. If low-level CPU archaeology interests you -- or you'd like to try a real-microcode 8086 as a soft CPU in your own project -- check out the project on GitHub: [👉 z8086 on GitHub](https://github.com/nand2mario/z8086). 

Feedback, issues, and PRs are always welcome. Thanks for reading!

