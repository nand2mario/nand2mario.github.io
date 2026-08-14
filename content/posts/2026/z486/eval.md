## Performance evaluation

### Dhrystone: CPU performance

Dhrystone provides a compact view of integer pipeline efficiency, largely
separate from clock rate and whole-system behavior. I ran Dhrystone 2.1 across
z386, ao486, z486, PicoRV32, and VexRiscv.

The benchmark uses the conventional VAX 11/780 normalization:

```text
DMIPS/MHz = iterations * 1,000,000 / (cycles * 1757)
```

All builds use `-O3 -fno-inline`, no link-time optimization, and no explicit
`register` declarations. The x86 cores execute the same i386 binary produced by
GCC 11.4. PicoRV32 and VexRiscv execute the same C source as RV32IM, built by
GCC 10.2. Memory responds at the earliest legal cycle. z386 and z486 retain the
release 8 KB instruction and 8 KB data caches; ao486 retains its native cache
organization. Results are fitted from 100, 1,000, and 10,000 iteration runs to
remove fixed marker cost.

| Core | Cycles/iteration | CPI | DMIPS/MHz | Cyclone V ALMs |
| --- | ---: | ---: | ---: | ---: |
| z386 | 2,526.4 | 4.101 | 0.225 | 15,545 |
| ao486 | 2,934.0 | 4.556 | 0.194 | 15,190 |
| **z486** | **1,725.0** | **2.800** | **0.330** | **21,906** |
| PicoRV32 | 2,336.1 | 4.172 | 0.244 | 1,202 |
| VexRiscv | 780.1 | 1.393 | 0.730 | 1,029 |

The ALM figures are standalone seed-1 fits on the DE10-Nano Cyclone V using
identical z486_MiSTer production settings. They are not an apples-to-apples
feature comparison: the RISC-V configurations omit caches, an MMU, x86
segmentation and protected mode, legacy I/O and interrupts, and floating point.
The z486 number includes its experimental x87; without x87, the integer core
uses 16,329 ALMs, only 5.0% more than z386.

<figure style="width: 100%; max-width: 820px; margin: 28px auto 32px;">
<img src="dhrystone_dmips_per_mhz.svg" alt="Locally reproduced Dhrystone DMIPS per MHz for z386, ao486, z486, PicoRV32, and VexRiscv" class="no-border">
<figcaption style="text-align: center;">Locally reproduced Dhrystone 2.1 efficiency. Higher is better. x86 and RISC-V use different binaries, so the RISC-V results are architectural context rather than an ISA-neutral ranking.</figcaption>
</figure>

z486 needs 31.7% fewer cycles per iteration than z386 and 41.2% fewer than
ao486. In normalized terms it is 46% faster per MHz than z386 and 70% faster
per MHz than ao486. At the tested MiSTer clocks, that corresponds to 28.05
DMIPS for z486 at 85 MHz, 19.15 for z386 at 85 MHz, and 17.46 for ao486 at
90 MHz. Source repositories, release clocks, and upstream benchmark results
are collected in [Further information and references](#further-information-and-references).

Changing z486's backing-memory model from the earliest legal response to a
five-cycle first read, one-cycle burst gap, and three-cycle write busy time
changes the fitted result only from 1,725.0 to 1,729.9 cycles per iteration
(0.3%). Once warm, this Dhrystone image fits in the split caches; the score is
primarily measuring the frontend and execution pipeline rather than SDRAM.

VexRiscv demonstrates how much easier this workload is for a compact RISC
pipeline: the local no-cache RV32IM build reaches 0.730 DMIPS/MHz. That is
still below the project's published 1.21 DMIPS/MHz for its full no-cache
configuration, which also assumes its documented benchmark and memory setup.
PicoRV32 reaches 0.244 DMIPS/MHz locally. Its project reports 0.516 with the
look-ahead memory interface and 0.305 without it. These gaps are a useful
warning that Dhrystone is highly sensitive to compiler and memory-interface
details, even before comparing different ISAs. The published PicoRV32 and
VexRiscv configurations are linked in the final reference section.

The ao486 retirement counter is taken at a different pipeline boundary, so its
CPI should not be compared as precisely as cycles per iteration or DMIPS/MHz.
All benchmark result checks passed, and the fitted cycle slopes have an
R-squared value above 0.9999999.

The complete runner records source and binary hashes, compiler versions,
iteration fits, cache settings, Quartus assignments, and fitted resources in
machine-readable JSON under `27.dhrystone_eval`. The local numbers should
therefore be treated as reproducible measurements; upstream frequency numbers
remain attributed reference data.

### Doom: whole-system performance

Doom is the performance target that matters most for this project. Unlike
Dhrystone, its timedemo exercises the complete PC system: instruction decode
and execution, caches, external memory, and video writes. These measurements
come from the same MiSTer setup at each core's release clock: 85 MHz for z386
and z486, and 90 MHz for ao486. The corresponding project and release records
are listed in [Further information and references](#further-information-and-references).

<figure style="width: 100%; max-width: 820px; margin: 28px auto 32px;">
<img src="integer_performance.svg" alt="Doom and 3DBench performance for z386, ao486, and z486" class="no-border">
<figcaption style="text-align: center;">Board-measured DOS performance on the same MiSTer setup. Higher is better.</figcaption>
</figure>

At maximum detail, z486 reaches 29.1 FPS in the Doom timedemo, 39% faster than
ao486's 21.0 FPS and 76% faster than z386's 16.5 FPS. The independent 3DBench
result shows the same ordering. This is the more representative measure of the
performance users see in DOS software, while Dhrystone makes it easier to
attribute that result to CPU pipeline efficiency.
