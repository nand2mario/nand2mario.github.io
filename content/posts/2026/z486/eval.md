## Performance evaluation

### Dhrystone: CPU performance

Dhrystone provides a compact measure of integer pipeline efficiency, largely
separate from clock rate and whole-system behavior. The evaluation covers
z386, ao486, z486, PicoRV32, and VexRiscv.

The benchmark uses the conventional VAX 11/780 normalization:

```text
DMIPS/MHz = iterations * 1,000,000 / (cycles * 1757)
```

All builds use `-O3 -fno-inline`, no link-time optimization, and no explicit
`register` declarations. The x86 cores execute the same i386 binary produced by
GCC 11.4. PicoRV32 and VexRiscv execute the same C source as RV32IM, built by
GCC 10.2. Each harness returns memory data at the earliest cycle allowed by its
interface. z386 and z486 retain the release 8 KB instruction and 8 KB data
caches; ao486 retains its native cache organization.

| Core | Cycles/iteration | CPI | DMIPS/MHz | Cyclone V ALMs |
| --- | ---: | ---: | ---: | ---: |
| z386 | 2,526.4 | 4.101 | 0.225 | 15,545 |
| ao486 | 2,934.0 | 4.556 | 0.194 | 15,190 |
| **z486** | **1,725.0** | **2.800** | **0.330** | **21,906** |
| PicoRV32 | 2,336.1 | 4.172 | 0.244 | 1,202 |
| VexRiscv | 780.1 | 1.393 | 0.730 | 1,029 |

The ALM figures come from standalone seed-1 fits on the DE10-Nano Cyclone V,
all using the same z486_MiSTer production settings. The configurations are not
feature-equivalent: the two RISC-V cores omit caches, an MMU, segmentation,
protected mode, legacy I/O and interrupts, and floating point. A z486 build
without x87 uses 16,329 ALMs, only 5.0% more than z386.

<figure style="width: 100%; max-width: 820px; margin: 28px auto 32px;">
<img src="dhrystone_dmips_per_mhz.svg" alt="Locally reproduced Dhrystone DMIPS per MHz for z386, ao486, z486, PicoRV32, and VexRiscv" class="no-border">
<figcaption style="text-align: center;">Locally reproduced Dhrystone 2.1 efficiency. Higher is better. x86 and RISC-V use different binaries, so the RISC-V results provide architectural context rather than an ISA-neutral ranking.</figcaption>
</figure>

z486 uses 31.7% fewer cycles per iteration than z386 and 41.2% fewer than
ao486. Its DMIPS/MHz is 46% above z386 and 70% above ao486. At the tested
MiSTer clocks, the results are 28.05 DMIPS for z486 at 85 MHz, 19.15 for z386
at 85 MHz, and 17.46 for ao486 at 90 MHz. Source repositories, release clocks,
and upstream results are listed in
[Further information and references](#further-information-and-references).

Compiler and memory-interface choices have a large effect on Dhrystone scores.
The local no-cache VexRiscv RV32IM build reaches 0.730 DMIPS/MHz, below the
project's published 1.21 DMIPS/MHz for its full no-cache configuration and
documented benchmark environment. PicoRV32 reaches 0.244 DMIPS/MHz locally;
its project reports 0.516 with the look-ahead memory interface and 0.305
without it. The published configurations are linked in the final reference
section.

CPI is derived from each binary's retired instruction count, so it should be
compared across ISAs less precisely than cycles per iteration or DMIPS/MHz.
The ao486 retirement event also occurs at a different pipeline boundary from
the z386 and z486 event. These differences do not affect the measured cycle
counts.

### Doom: whole-system performance

Doom measures whole-system performance rather than isolated integer pipeline
efficiency. Its timedemo exercises instruction decode and execution, caches,
external memory, and video writes. All measurements use the same MiSTer setup
at each core's release clock: 85 MHz for z386 and z486, and 90 MHz for ao486.

<figure style="width: 100%; max-width: 820px; margin: 28px auto 32px;">
<img src="integer_performance.svg" alt="Doom and 3DBench performance for z386, ao486, and z486" class="no-border">
<figcaption style="text-align: center;">Board-measured DOS performance on the same MiSTer setup. Higher is better.</figcaption>
</figure>

At maximum detail, z486 reaches 29.1 FPS in the Doom timedemo, 39% faster than
ao486's 21.0 FPS and 27% faster than z386 v0.4's 23.0 FPS. The independent
3DBench result shows the same ordering. Doom represents complete DOS-system
behavior; Dhrystone more directly isolates integer pipeline efficiency.
