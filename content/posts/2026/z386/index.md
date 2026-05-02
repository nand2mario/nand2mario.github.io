---
title: "z386: Rebuilding the 80386 from Original Microcode"
date: 2026-04-30T20:00:00+08:00
draft: true
sidebar: false
comment: true
author: nand2mario
tags: [386]
---

This is the fifth installment of the [80386 series](/tags/386/). The z386 FPGA CPU is finally built, and this post is about how it works. [z386](https://github.com/nand2mario/z386) is a 386-class CPU built around the original Intel microcode, in the same spirit as [z8086](/posts/2025/z8086/). It implements most of the 80386 architecture: real mode, protected mode, 32-bit address and data paths, paging, interrupts, call gates, descriptor caches, and many of the corners that make the 386 more than a widened 286.

The core is not an instruction-by-instruction emulator in RTL. The goal is to recreate enough of the original machine that the recovered 386 control ROM can drive it. That means some timings also resemble the real chip. For example, the simplest register-to-register instructions still take two microcode cycles. Today z386 boots DOS 6 and DOS 7, runs EMM386, and gets into real DOS games such as Doom. Here are some rough numbers against ao486:

| Metric | z386 | ao486 |
| --- | ---: | ---: |
| Lines of code, by C LOC | 8K | 17.6K |
| ALUTs | 18K | 21K |
| Registers | 5K | 6.5K |
| BRAM | 116K | 131K |
| Frequency | 85MHz | 90MHz |
| 3DBench FPS | 34 | 43 |
| Doom (original) FPS, max details | 16.5 | 21.0 |

In current builds, z386 feels roughly like a 70 MHz 386 with a decent cache, or a 35 MHz 486. It runs at a much higher clock than a historical 386, but with different CPI tradeoffs because it is mapped to FPGA resources rather than to Intel's 1980s process. The current cache is a 16 KB 4-way set-associative unified L1, chosen partly to keep the clock high. Contemporary high-end 386 systems often used larger external caches, typically in the 32 KB to 128 KB range.

<figure>
<img src="z386_doom2_game.jpg" alt="Doom II running on z386" class="no-border">
<figcaption style="text-align: center;">Doom II running on z386.</figcaption>
</figure>

A lot of the 386 design has already been covered in the previous four posts: the [multiplication/division datapath](../80386_multiplication_and_division/), the [barrel shifter](../80386_barrel_shifter/), [protection and paging](../80386_protection/), and the [memory pipeline](../80386_memory_pipeline/). z386 tries to be both an educational reconstruction and a usable FPGA CPU. It keeps many 386-like structures: a 32-entry paging TLB, a barrel shifter shaped like the original, ROM/PLA-style decoding, the protection PLA model, and most importantly the 37-bit-wide, 2,560-entry microcode ROM. At the same time, it uses FPGA-friendly shortcuts where they make sense, such as DSP blocks for multiplication and a small fast L1 cache.

In this post, I will fill in the rest of the design: instruction prefetch, decode, the microcode sequencer, testing, the PC system around the CPU, cache design, timing pressure, and some lessons from the bring-up.

<!--more-->

## From z8086 to z386

A little background first. Last year I wrote [z8086](https://github.com/nand2mario/z8086), an original-microcode-driven 8086 based on [reenigne's disassembly work](https://www.reenigne.org/blog/8086-microcode-disassembled/). That project showed that building a working CPU around recovered microcode was possible. Near the end of the year I learned that 80386 microcode had recently been extracted and that reenigne was working on a disassembly. He generously shared that work with me, and z386 started from there.

The 386 is a very different problem from the 8086. The instruction set is larger, the internal state is much richer, and the machine has to enforce protection, paging, privilege checks, and precise faults. More importantly, the 80386 micro-operations are denser and more contextual. If the 8086 microcode reads like a straightforward C program, the 386 microcode reads more like hand-tuned assembly: short, subtle, and full of assumptions about hidden hardware.

That puzzle took about four months of evenings and weekends. The result is not a perfect 386 yet, but it is now far enough along to run real protected-mode DOS software.

## z386 - the 10K feet view

At a high level, the 386 is organized around eight major units. z386 follows the same division closely enough that the original Intel block diagram is still a useful map.

<figure>
<img src="80386-blockdiagram.png" alt="80386 block diagram showing bus interface, prefetch, instruction decode, control, data, protection test, segmentation, and paging units" class="no-border">
<figcaption style="text-align: center;">The 80386 as eight cooperating units.<br>
<small>Source: Intel, <i>The Intel 80386 - Architecture and Implementation</i>, Figure 8.</small></figcaption>
</figure>

The diagram actually maps quite well to the actual 386 die shot, although the relative positions of the units are different.

<figure>
<img src="80386-die-labeled-units.jpg" alt="Intel 80386 die shot labeled with the major functional units" class="no-border">
<figcaption style="text-align: center;">The same eight-unit organization on the 80386 die.<br>
<small>Base image: <a href="https://commons.wikimedia.org/wiki/File:Intel_80386_DX_die.JPG">Intel 80386 DX die</a>, Wikimedia Commons.</small></figcaption>
</figure>

Here is what those units do in z386:

**1. Prefetch unit.** Keeps a 16-byte instruction queue filled from memory. Branches, faults, interrupts, and segment changes can flush and restart it.

**2. Decoder.** Consumes instruction bytes, tracks prefixes, recognizes ModR/M and SIB forms, gathers immediates and displacements, and maps instructions to microcode entry points.

**3. Microcode sequencer.** Fetches expanded microcode words, handles jumps, delay slots, faults, and run-next-instruction behavior.

**4. ALU and shifter.** Implements arithmetic, logic, flags, bit operations, shifts, rotates, multiplication, and division support.

**5. Segmentation unit.** Computes logical-to-linear addresses, applies segment bases and limits, and stores the hidden descriptor-cache state.

**6. Protection unit.** Recreates the 386 protection PLA behavior for selector and descriptor validation.

**7. Paging unit.** Handles TLB lookup, page walks, Accessed/Dirty updates, page faults, and the transition from linear to physical addresses.

**8. BIU/cache/memory path.** Connects CPU memory operations to paging, cache, SDRAM, ROM, I/O, and the surrounding PC system.

This organization is not a modern uniform pipeline. The 386 is better thought of as several large, partly independent state machines that overlap: prefetch can run while the execution unit is busy, decode can prepare later instructions, address translation can start before the bus is needed, and protection tests can redirect the sequencer a few cycles later. Intel's papers describe up to six instructions being in different phases of processing at once, but the execution unit still consumes one micro-instruction per cycle. Unlike the 486 and later processors, which reorganized the design into a finer-grained pipeline aimed at one instruction per clock, the 386 still needs at least two microcode cycles for even simple register-register instructions.

Previous posts covered units 4 through 8 in some depth. Here let's start with the front end: prefetch, decode, and the microcode sequencer.

## Instruction Prefetch

One surprise from z8086 was how much the 8086 is limited by its instruction queue bandwidth. The 8086 can fetch one byte at a time from the queue into the execution side. That is simple and compact, but it becomes a bottleneck as soon as instruction bytes are consumed faster than they are replenished.

The 386 front end is wider because the math changes. Jim Slager's ICCD 1986 paper, "Performance Optimizations of the 80386", gives the useful back-of-the-envelope calculation: the average 80386 instruction is about four bytes long, and the weighted average instruction takes about four clocks, so steady-state execution needs about one byte of code per clock. The external bus can read four bytes every two clocks, so raw bus bandwidth is not the limiting factor. The harder problem is smoothing bursts from variable-length instructions, branches, and data cycles stealing bus slots from prefetch.

The same paper describes the 386 instruction pipe as a bus unit, a prefetch unit, and an instruction unit. The prefetch unit fills a 16-byte code queue, and the instruction unit formats decoded instructions into a three-entry instruction queue. z386 follows the first part directly: it has a 16-byte prefetch queue, internally stored as four 32-bit words. It exposes two views to the decoder: the next byte, and a 32-bit window starting at the current byte offset. That lets the structural part of decode proceed byte by byte, while literal fields such as displacement and immediate data can be swallowed in 1-, 2-, or 4-byte chunks.

<figure>
<img src="z386_frontend_pipeline.svg" alt="z386 front-end pipeline from cache and memory to prefetch, decode, decoded queue, and microcode sequencing" class="no-border">
<figcaption style="text-align: center;">The z386 front end keeps byte-at-a-time structure decode, but exposes a wider window for displacement and immediate fields.</figcaption>
</figure>

This is a small but important difference from the 8086 model. A 386 instruction may contain prefixes, an opcode, a ModR/M byte, a SIB byte, a displacement, and an immediate. The prefix/opcode/ModR/M part controls what the instruction is, so reading it one byte at a time keeps the logic understandable. But once the decoder knows that the next four bytes are just a displacement, there is no architectural reason to spend four separate cycles collecting them.

The queue depth is also a compromise. A deeper queue hides more memory jitter, but it costs storage and makes flush recovery more expensive. A wider queue output improves decode throughput, but it creates FPGA timing pressure because the byte window depends on a rotating pointer and may cross a 32-bit word boundary. z386's current 16-byte queue and 4-byte window are a practical middle point: wide enough not to be the normal bottleneck, small enough to keep the front end fast.

## Decode

x86 instruction decoding is hard because the instruction boundary is not obvious. There may be several prefixes, then an opcode, maybe a `0F` escape opcode, maybe a ModR/M byte, maybe a SIB byte, then displacement and immediate fields whose sizes depend on mode bits and earlier bytes. A decoder has to discover the structure of the instruction while it is still reading it.

The lesson from z8086 was that byte-at-a-time decode is much easier to reason about. The 386 designers seem to have kept that idea for the structure-deciding bytes: prefixes, opcode, and ModR/M are still processed as a small state machine. Slager's paper makes the other half explicit: the 80286 instruction preparation unit handled exactly one byte per clock, which was enough for its shorter average instruction length, but the 386 needed more because 32-bit addressing adds four-byte displacements and immediates. Its instruction preparation unit can handle two- or four-byte displacements and immediates in a single clock, for about 1.5 bytes of code per clock in actual operation.

z386 follows that pattern. The decoder has states for idle/opcode, ModR/M, SIB, displacement, immediate, and done. In the opcode state it handles prefixes and asks the control PLA what kind of instruction layout this byte implies. In the ModR/M state it decides register fields, memory forms, SIB presence, and displacement size. In the displacement and immediate states it uses the 32-bit prefetch window to take up to four bytes at once.

For example, the byte stream `67 8B 44 24 08` is not decoded as one table lookup. The decoder learns its shape as it goes:

| Byte | Meaning | Decoder action |
| --- | --- | --- |
| `67` | Address-size prefix | Set address-size override and keep scanning. |
| `8B` | `MOV r32, r/m32` | Ask ROM1 for the layout; ModR/M follows. |
| `44` | ModR/M | Memory form; SIB follows; displacement is 8 bits. |
| `24` | SIB | Select base and index fields for effective address generation. |
| `08` | disp8 | Capture displacement and finish the decoded instruction record. |

This makes a visible difference. A near jump with a 32-bit displacement, or a memory instruction with a SIB byte and disp32, should not spend most of its time merely collecting constant bytes. z386's decoder can push a completed decoded-instruction record into a small queue, so the microcode engine can start the instruction without re-reading the raw bytes.

The cost is timing. One of the recurring hard paths in z386 runs from the prefetch queue pointer, through the byte-selection window, through PLA-style decode logic, and into the decoded-instruction queue. That path is exactly where the architecture wants the hardware to be wide and quick, while the FPGA wants short registered logic.

It also makes decode bugs more interesting. Recent protected-mode tests used byte streams such as `F3 AA 8B 44 24 08...` and `F3 AA B8 33 00 00 00...`. The important part was not `REP STOSB` itself, but what happened after it: the decoder had to finish the string instruction cleanly and not let stale prefix or ModR/M state poison the following instruction. Variable-length x86 decode is a state machine, not just a table lookup.

### ROM-based instruction decode

The 386 decoder is not just handwritten random logic. It uses ROM/PLA structures, similar in spirit to the 8086 "Group Decode" ROM but more elaborate. In z386 I model two main pieces: the control PLA (`pla_control`, corresponding to ROM1) and the entry PLA (`pla_entry`, corresponding to decoder ROM2/ROM3).

The control PLA answers the structural question: what kind of instruction am I looking at? z386 feeds it with:

```
{decode_state[6:0], current_byte[7:0], mode[4:0]}
```

The mode bits include the `0F` escape state, whether 32-bit addressing is active, whether a SIB byte follows, and the special 16-bit and 32-bit displacement-only ModR/M forms. In the opcode state, the 12-bit ROM1 output tells z386 whether the byte is a prefix, whether ModR/M follows, whether opcode bits contain an embedded register, whether the opcode has a W bit, whether flags are updated, and what immediate-size class is expected. In the ModR/M state, the same output bits mean something different: SIB present, memory/register form, and displacement class.

The entry PLA answers the execution question: where does the microcode start? The first pass uses operand size, opcode, REP state, protected-mode state, and the `0F` escape flag. For group opcodes, the first pass returns a compact intermediate value. After the ModR/M byte is known, a second pass uses the ModR/M `reg` field and memory/register form to choose the final microcode entry point.

For example, opcode `89` alone only says "MOV r/m, r" and that a ModR/M byte is needed. If the ModR/M byte is `C0`, the second pass sees that the operand is register-register and maps the instruction to the `MOV r,r` microcode entry at `003`. If the ModR/M byte names memory, it maps to a memory move routine instead.

This style is important because it keeps decode table-driven without making one huge table over every possible instruction byte sequence. It also matches the reverse-engineering picture: ROM1 classifies layout, while ROM2/ROM3 choose microcode entry points.

There are still open questions. z386 uses the ROM1 lines needed by the current decoder, but many recovered lines are still unused or only partly understood. Understanding more of ROM1 may let the decoder become smaller and faster. The protection PLA, which I call ROM4 or PLA4, has a similar status: enough is understood to run real software, but not every input and output has a perfect historical explanation yet.

## Microcode sequencer - the Control Program

z386 uses the original Intel 386 microcode as its main control program. The ROM decides which internal values move, when the ALU runs, when memory cycles start, when the sequencer branches, and when the next x86 instruction may begin. The RTL does not implement `ADD`, `IRET`, or `SGDT` as large behavioral blocks. It implements the hardware that the microcode expects to control.

Each micro-instruction is 37 bits wide. In the disassembly I use these fields:

<figure>
<img src="microcode_word.svg" alt="37-bit 80386 microcode word split into source, destination, ALU source, ALU jump, op, sub, and bus fields" class="no-border">
<figcaption style="text-align: center;">The 37-bit microcode word as used by the z386 disassembly.</figcaption>
</figure>

```
source  -> dest    alu_src        alu/jump op  sub bus
```

The source and destination fields select internal registers and datapath endpoints. The ALU source and ALU/jump fields choose an ALU operand, ALU operation, or branch target. The op/sub fields encode special sequencer and size behavior. The bus field starts reads, writes, prefetch flushes, descriptor-cache operations, and address-pipeline operations.

A simple register-register move shows why the 386 has a two-cycle minimum:

```
003  SRCREG                           PASS    RNI          0
004  SIGMA  -> DSTREG
```

The first micro-instruction selects the source register and passes it through the ALU, while also marking the instruction as `RNI`, or run next instruction. The second micro-instruction is the delay slot that writes `SIGMA` to the destination register. On a 486-style pipeline, that second action would look more like a writeback stage overlapped with later instruction work. On the 386, it is still a serialized microcode cycle. This is one reason the 386 cannot reach one instruction per clock even for simple operations.

The notation also hides a lot of subtlety. `EAX` and `eAX_AL` are not the same kind of destination: one is the full architectural register, while the other is size-aware and can target AX or AL depending on the current operand size. `EIP`, `eIP`, and `IP` likewise differ in how they apply code-segment and operand-size rules. These distinctions matter because the microcode relies on them instead of spelling out every width case explicitly.

Control flow has its own traps. Microcode jumps have delay slots. `RNI`, `RnI`, and `RNi` are different end-of-instruction variants. Protection tests have a longer latency: after a PLA4 test redirects the sequencer, three more micro-instructions still execute. The original microcode uses those slots deliberately, so z386 has to preserve them rather than "fix" them away.

This is powerful, but unforgiving. A micro-op name is not always enough:

- `LLIM` is a cached-limit read, not a descriptor-cache write.
- `LBAS` reads a cached descriptor-table base.
- `WR D` is a distinct dword write bus operation.
- `SDEL` can load descriptor-low data from different internal sources depending on the microcode field.

Each of these details caused real boot failures before the surrounding hardware matched what the microcode expected.

`SGDT` was a good example. The visible instruction is simple: store the GDTR limit and base to memory. But the microcode uses cached descriptor-table state through `LLIM` and `LBAS`, then stores the 32-bit base with `WR D`. Treating `LLIM` as a descriptor-cache write corrupted the hidden GDTR cache. Implementing `LBAS` fixed the source value, but the base still did not store until `WR D` was recognized as its own memory operation. One instruction exposed three separate assumptions hidden behind short micro-op names.

The project therefore started with three reverse-engineering steps before the CPU itself was useful: parse the CROM, understand the ROM1 instruction-layout decoder, and reproduce the ROM2/ROM3 entry-point decoder. The first working z386 was not a hand-written x86 emulator. It was a small machine trying to obey the recovered control ROM and decoder PLAs.

## Testing

I expected the 386 to be harder than z8086 because protected mode is much more complicated. The surprise was the shape of the work. It took about a month to write most of the first core, and then about three more months to make it run Doom. The code was not the long pole. The long pole was finding all the small hidden contracts needed by BIOSes, memory managers, DOS extenders, and games.

The most important base test suite is [SingleStepTests/80386](https://github.com/SingleStepTests/ProcessorTests), generated by [gloriouscow](https://github.com/dbalsom). It compares architectural state after single instructions and catches a huge class of real-mode bugs: arithmetic, flags, addressing modes, prefixes, stack behavior, string instructions, and exception boundaries.

Real-mode tests were not enough, so I built a protected-mode counterpart using 86Box as the reference: [SingleStepTests_80386_protected](https://github.com/nand2mario/SingleStepTests_80386_protected). Protected-mode single-step tests are especially valuable because they isolate instructions such as `IRET`, `LSS`, `SGDT`, `LAR`, gate transfers, page faults, and selector loads without requiring a whole DOS boot around them.

I also added hand-written protected-mode programs for cases that are hard to express as one isolated instruction: call gates, cross-privilege calls, interrupt gates, trap gates, `STI` and `MOV SS` interrupt shadows, hardware interrupt wakeup from `HLT`, real/protected-mode transitions, VM86 interrupt stack behavior, prefetch flush loops, and stale ModR/M state. These tests are not glamorous, but they are the difference between "runs simple protected-mode code" and "survives EMM386".

Other tests fill different roles. `test386.asm` is a broad historical compatibility test. SeaBIOS is useful because it can be rebuilt to print debug information over an I/O port, making early boot much less opaque. FreeDOS, DOS 6/7, HIMEM, EMM386, DOS/4GW, DOS/32A, Doom, FastDoom, and other games then become full-system integration tests.

DOS extenders were especially painful. DOS/4GW took roughly two weeks of tracing and disassembly before the core could get through enough of its protected-mode setup. I used Ghidra to understand parts of the extender, but in hindsight an open-source extender would have been easier to instrument. DOS/32A and EMM386 later became better debugging targets because their behavior could be correlated with listings, memory maps, and repeatable traces.

The most useful debugging loop has been:

1. Run a real program until it diverges.
2. Capture a waveform.
3. Locate the current `CS:EIP`.
4. Reconstruct instruction bytes from prefetch reads.
5. Compare with a known-good trace.
6. Reduce the finding to a focused test when possible.

This is slow, but it works. It found CPU bugs, cache bugs, reset bugs, IDE bugs, and generated-memory bugs. One board-only failure came from `ucode45.hex` and `ucode45.mif` getting out of sync. Verilator used the HEX file, while Quartus used the stale MIF file, so simulation and FPGA were literally running different expanded microcode data.

There is still much more to test. Windows does not work yet, and protected-mode coverage is not complete. But the current tests have already changed how I think about CPU bring-up: single-instruction tests make the core believable, while full-system software makes it honest.

## From CPU Core to PC System

Another earlier lesson was that a CPU core is not enough to boot interesting software. The project gradually accumulated a PC around z386: BIOS ROM loading, CMOS, PIC, PIT, keyboard controller behavior, IDE, A20, VGA, Sound Blaster DMA, and eventually MiSTer/386Tang wrappers.

Some bugs looked like CPU bugs but were really PC integration bugs. An interrupt acknowledge cycle has two phases, and returning the vector too early produced the wrong interrupt number. A hardware interrupt taken in the same cycle as `i_pop` once skipped a `POP` instruction: EIP advanced, but the microcode writeback never happened, so IRET returned past an instruction whose stack effect was lost. IDE behavior also mattered: DOS 7.1 used ATA paths that DOS 6.22 and FreeDOS did not, so the disk backend had to become more faithful before the CPU could be debugged further.

This is why full-system traces became so important. When the machine is booting BIOS and DOS, `CS:EIP` alone is not enough. You need to know which interrupt just happened, what the PIC returned, whether A20 is enabled, whether an IDE write was acknowledged correctly, and whether the VGA or BIOS region is write-protected.

## Cache: Making Memory Feel 386-like

The original 386 has no on-chip L1 cache, but it is not a pre-cache design. Intel expected high-performance systems to use local SRAM or external cache controllers such as the 82385. In that world, many code and data reads could complete with zero wait states, while slower DRAM accesses were hidden behind bus pipelining, prefetch buffering, and data-over-prefetch priority.

That matters for z386 because the microcode timing assumes memory can often answer quickly. A typical memory operation is `RD`, then `DLY`, then use `OPR_R`. If every access has to go through SDRAM latency, the core remains correct but spends too much time stalled in `DLY`. Early z386 could run from SDRAM directly, but 3DBench showed high CPI and heavy contention between instruction prefetch and data reads.

The current FPGA memory path adds a unified L1 cache behind the BIU, with an early lookup sideband from the paging path:

<figure>
<img src="cache_path.svg" alt="z386 cache and memory path with segmentation, paging, VIPT preread, tag compare, write buffer, and SDRAM fill" class="no-border">
<figcaption style="text-align: center;">The z386 memory path starts the cache preread from the linear page offset, then compares physical tags when paging finishes.</figcaption>
</figure>

| Parameter | z386 cache |
| --- | --- |
| Size | 16KB |
| Line size | 16 bytes, 4 DWORDs |
| Associativity | 4-way set associative |
| Replacement | PLRU |
| Policy | unified I+D, read-allocate, write-through |
| Write buffer | 2 entries |
| Fill | SDRAM burst fill, early restart |
| Lookup | VIPT preread, physical tag compare |
| Hit latency | zero-wait hit response after preread |

Unified I+D is important because the 386-style prefetch unit and data accesses share the memory path. A hit avoids SDRAM traffic entirely, which removes both latency and prefetch/data contention. The write buffer lets stores retire without waiting for SDRAM when possible. Early restart forwards the requested DWORD as soon as it appears during the burst fill, instead of waiting for the whole line to finish. The VIPT lookup starts the tag and data BRAM preread from the linear page-offset bits one cycle before the physical request arrives; the next cycle compares the physical tag against the registered tags and can return a hit immediately.

This was not just a performance feature; it became a correctness and timing feature too. One cache bug came from a burst-fill BRAM write colliding with a same-cycle read of the newly valid line, returning stale data. Another came from write-buffer drain and cache fill fighting for the same memory request register. Later timing reports also showed cache, paging, BIU ready, and microcode stall signals forming feedback paths. A cache that is logically correct but one cycle too late changes how long the microcode waits, and a cache that is fast but poorly decoupled can become an Fmax bottleneck.

The lesson was that "add a cache" is too vague. For this kind of core, the cache has to match the 386 memory protocol. The useful target is not only high hit rate, but a hit path short enough that `DLY` often behaves like the zero-wait-state local-cache systems the real 386 was designed to use.

## Fmax Pressure

The other big difference from z8086 is timing.

z8086 is small enough that most timing problems are local. z386 has timing paths that cross subsystem boundaries. Some current examples are:

- prefetch queue to decoder to decoded-instruction queue
- shift result and flag generation into EFLAGS
- paging/cache/BIU ready signals feeding back into CPU stall and microcode sequencing
- high-fanout mode bits such as operand size and protected-mode state

This is where the 386 becomes difficult as an FPGA core. A simulator only asks whether the logic is correct. Quartus asks whether the logic is short enough to run at the target clock. Those are different questions.

One recent experiment was an Altera-specific ALU variant to encourage better carry-chain mapping on DE10-Nano. It helped, but the top timing paths then moved elsewhere. That is normal timing work: once one obvious bottleneck is removed, the design reveals the next one.

The hard part is deciding which timing fixes are architecturally safe. Adding a register may improve Fmax, but if it changes when the microcode sees a memory completion, a decoder result, or a fault, it may also change CPU behavior. With a microcode-driven core, timing fixes have to preserve the contract expected by the microcode.

This is why the official 386 papers are useful even for an FPGA implementation. They remind you that the original chip solved performance with overlap: early-start address calculation, pre-decoded instruction queues, prefetch filling dead bus slots, TLB lookup in parallel with linear address generation, and special hardware for protection checks. If z386 falls back to serializing those paths, it may remain correct but it will not feel like a 386.

## z386 and ao486

There is already a mature FPGA x86 core: ao486. It is widely used, practical, and much further along as a compatibility target. But the interesting difference is not just 386 versus 486. It is the kind of pipeline each design is built around.

The original 386 is a coarse-grained pipelined machine. Its large units - bus, prefetch, instruction decode, execution, data, protection, segmentation, and paging - run mostly autonomously and overlap with each other. The instruction unit prepares decoded instruction-queue entries. The execution unit then runs one original microcode routine against that decoded instruction, with delay slots and `DLY` waits exposing timing contracts to the surrounding hardware. Parallelism comes from unit-level overlap: prefetch can fill the code queue, decode can prepare later instructions, the address pipe can work on memory references, and the bus can arbitrate code and data traffic.

The 486 moves toward a finer-grained pipeline. Crawford's i486 paper describes a five-stage flow: Fetch, D1, D2, Ex, and WB. Fetch moves 16 bytes from the on-chip cache into the prefetch queue. D1 performs the main instruction decode. D2 finishes secondary decode and computes memory addresses. Ex executes the operation, often in parallel with cache lookup. WB commits the result. The on-chip 8KB unified cache, wider prefetch path, and address computation in D2 are all part of the one-clock-per-instruction goal.

ao486 follows that finer-grained style as an FPGA implementation. Its core is organized around fetch, decode, read, execute, and writeback stages, with command records, step/ready signals, flushes, and resource mutexes to manage hazards. Complex x86 instructions still become multi-step sequences, but they are expressed as staged command flow rather than as original 386 microcode driving a reconstructed 386 datapath.

| Topic | z386 / 386 style | ao486 / 486 style |
| --- | --- | --- |
| Main organization | Large cooperating units | Finer pipeline stages |
| Control model | Original 386 microcode ROM drives reconstructed hardware | Staged command flow implements x86 behavior |
| Front end | Prefetch queue, PLA decode, decoded instruction queue | Fetch and decode stages feeding later pipeline work |
| Memory model | 386-like segmentation, paging, cache, and bus timing contracts | 486-style cache-centered pipeline organization |
| Timing risk | Coarse steps can expose long cross-unit paths | Stage boundaries make many hazards explicit |
| Debugging flavor | Hidden state and microcode timing assumptions | Stage transitions, command sequencing, and resource conflicts |

That makes the projects useful in different ways. ao486 is the pragmatic compatibility core: proven, 486-class, and designed around a staged implementation. z386 is closer to CPU archaeology: it asks what hardware must exist for the recovered 386 microcode, decoder PLAs, protection PLA, descriptor caches, and paging machinery to make sense. In ao486, an interesting bug often lives at a stage boundary, hazard rule, or command step. In z386, it often lives in a hidden state update or a microcode timing assumption.

This also changes the timing problem. ao486 has many explicit stage boundaries. z386 has fewer, larger architectural steps, so preserving a 386 timing contract can leave a microcode word, decoded instruction fields, address calculation, protection decision, and memory response interacting in the same coarse step. z386 is not trying to be a slower ao486. It is exploring a different machine organization: less like a uniform five-stage pipeline, more like the original 386 collection of large overlapping units.

## Current Status

z386 is still a work in progress, but it has reached the point where real software is the main test case.

It can boot BIOS and DOS paths in simulation, run protected-mode setup code, load EMM386, and get far enough into DOS extenders and Doom to expose deep memory-management bugs. Several recent fixes came from comparing z386 traces against known-good traces through EMM386, DOS/32A, and FastDoom.

Roughly, the project timeline has looked like this:

- **January.** Parsed the CROM, reproduced ROM1 and ROM2/ROM3 decoding, built the first z386 core, then pushed through real-mode instruction coverage: instruction queue, ALU, ModR/M and SIB addressing, stack operations, shifts, strings, multiply/divide, interrupts, fault handling, and the real-mode single-step / `test386.asm` suites.
- **February.** Built the protected-mode core: segmentation, paging, TLB and page walker, descriptor loading, PLA4 protection tests, call gates, interrupt gates, page faults, VM86 support, A/D bit write-back, and the 86Box-based protected-mode test generator. By the end of the month, SeaBIOS and FreeDOS were running in full-system simulation.
- **March.** Moved from CPU tests into hardware and system work: 386Tang on Tang Console 138K, SDRAM, VGA/HDMI, keyboard, IDE, Sound Blaster DMA, cache/CPI experiments, timing cleanup, HIMEM/unreal-mode debugging, and the first real DOS/game workloads such as 3DBench and Speed600.
- **April.** Focused on Doom, DE10-Nano/MiSTer, and timing closure: DOS/4GW and DOS/32A fixes, Sound Blaster audio, larger L1 cache experiments, DE10-Nano boot, 75-85MHz timing sweeps, MiSTer HPS/IDE/BIOS integration, DOS 7.1 + EMM386 debugging, and the current Altera-specific ALU/timing work.

On FPGA, the remaining work is a mixture of correctness and timing closure. The core is large enough that Fmax is now an architectural concern, not just a synthesis setting. Decoder, paging, cache, and flag-generation paths all need careful work.

## Lessons So Far

The first lesson is that original microcode is incredibly valuable, but it is not a complete CPU description. The ROM tells you what the control program does. It does not fully tell you what each hardware unit computes, when hidden state changes, or how long a protection redirect takes.

The second lesson is that protected mode is the center of the 386. A simple real-mode instruction core can look convincing for a while, but EMM386, paging, gates, faults, and descriptor caches quickly reveal whether the machine is really 386-like.

The third lesson is that tests need layers. Single-instruction tests find local bugs. BIOS and DOS find system bugs. Doom and DOS extenders find bugs in the interaction between everything.

Finally, FPGA timing is part of the architecture. The original 386 had dedicated PLAs, custom datapaths, and carefully balanced timing. Rebuilding it on an FPGA means rediscovering not only the logic, but also where the original design relied on parallelism and short custom paths.

That is what makes the project fun. z386 is part CPU implementation, part archaeology, and part timing puzzle. The 386 is just close enough to be understandable, and just complicated enough to keep producing surprises.

Credits: The anlaysis of the 80386 in this post draws on the microcode disassembly and silicon reverse engineering work of [reenigne](https://www.reenigne.org/blog/), [gloriouscow](https://github.com/dbalsom), [smartest blob](https://github.com/a-mcego), and [Ken Shirriff](https://www.righto.com).
