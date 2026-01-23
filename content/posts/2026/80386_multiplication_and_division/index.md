---
title: "80386 Multiplication and Division"
date: 2026-01-23T09:10:12+08:00
draft: true
sidebar: false
comment: true
author: nand2mario
---

This is the first post of a series recording the building of a FPGA core similar to the 80386.

The Intel 80386 is a legendary microprocessor in computer history. Arguably it is the most important Intel x86 processor, as it established the 32-bit x86 standard architecture, running operating systems like Windows 95 and Linux. 

The 386 has many advanced features, compared with the original 8086. One advantage is it can do complex math operations faster. Its can do multiplication and division at the speed of **one bit per cycle**. In comparison, on the 8086, 16-bit multiplication takes ~120 cycles and division takes ~150 cycles.

Both multiplication and division use iterative algorithms implemented as inline datapath logic that advances once per microcode cycle - that's where the timing of one bit per cycle comes from. To save space, the main ALU is reused for per-iteration add/subtract work. Several types of microcode operations are dedicated to doing multiplication and division.

## Add-and-shift multiplication

The classic multiplication algorithm in processors is the Booth algorithm. However, the 80386 does not use that, instead an "add-and-shift" multiplication algorithm is used. This is similar to grade-school long multiplication. The difference is that instead of moving from lower digits to higher, we shift to the right. Here's the data layout:

```
   MULTMP    ,    TMPB           ->
multiplicand    multiplier  

   +---------------------------------------------+ 
   |         |        product         |          |
   +---------------------------------------------+
   |       SIGMA         ||         TMPB         |
   +---------------------------------------------+
                64-bit accumulator
```

Three internal registers are involved in multiplication: MULTMP, TMLB and SIGMA. One small challenge is x86 supports 8-bit, 16-bit and 32-bit operations. As in the 8086, reuse and parameterization is the theme here. In most cases, the same registers and microcode routine handles instructions with different operand widths. The above diagram actually illustrates the layout for the 32-bit product after multiplying two 16-bit numbers - it occupies the lower half of the 32-bit SIGMA and upper half of TMB.

So here's the multiplication algorithm in pseudocode:

```c
1: COUNTR = width-1
2: while (true):
3:   if (TMPB[0]) SIGMA <= SIGMA + MULTMP
4:   {SIGMA, TMPB} >>= 1
5:   if (--COUNTR==0) break
6:   if ((TMPB & (1<<COUNTR-1)) == 0) break
7: {SIGMA, TMPB} >>= COUNTR
8: correction for signed multiplication
```

Shifting to the right instead of left makes the circuits simpler. Line 6 is the so-called "early-out" optimization - exiting the loop early when the remaining multiplier bits are all zero. Then line 7 compensates for that early exit by shifting the result to the right by the remaining COUNTR bits.

Line 1-7 covers the unsigned multiplication fully. It turns out supporting signed multiplication only requires arithmetic shifts on line 4 and 7, and a finally correction: subtracting the multiplicand from the higher part of product (SIGMA) if the multiplier is negative, on line 8. Refer to college computer organization materials, e.g. [this](https://web.ece.ucsb.edu/~parhami/pres_folder/f31-book-arith-pres-pt3.pdf), for the underlying math.

The 80386 multiplication microcode is a direct realization of the algorithm above, giving a clearer view of the timing and hardware structure of the implementation. The following routine covers both unsigned and signed register multiplication of all 3 different operand sizes (8, 16 and 32 bits). Other variants (like memory operand) are similar. 

The 80386 microcode has more fields than the 8086 format. Each micro-instruction is 37 bits wide, compared with 21 bits of the 8086. In the listing below, `src->dest` is a register MOVE (copy) operation. At the same time, `alujmp` could control the ALU or sequencer to do arithmetic (`src` and `alu_src` are two inputs to the ALU), jump to another microcode location (`alu_src` is the destination in this case), and do other operations. One relevant keyword here is `RPT` on line 1A7. It controls the microcode sequencer to repeat the same micro instruction and decrement COUNTR (an internal register) until it is 0, for a total of COUNTR+1 times.

```asm
; MUL/IMUL r
; src     dest    alu_src        alujmp  uop sub busop
DSTREG -> MULTMP  BITS_V         LDCNTR                ; MULTMP=r (multiplicand), COUNTR=BITS_V (7,15 or 31 depending on operand size)
eAX_AL -> TMPB    0              PASS2                 ; TMPB=multiplier (AL/AX/EAX)
SIGMA             TMPB           IMUL3   RPT DLY       ; hardware multiplication loop, early-out if remaining all 0 or all 1
SIGMA                            PASS                  ; pass through SIGMA
COUNTR -> TMPD                                         ; save remaining COUNTR for shift calculation
RESULT -> TMPC    TMPD           LDBSR8                ; load barrel shift count: right shift COUNTR (TMPD) bits
SIGMA  -> TMPD    TMPC           SHIFT                 ; shift {SIGMA, RESULT} (total width 2*width) by COUNTR to extract low result
SIGMA  -> eAX_AL  TMPD           MULFIX                ; write low result, set flags, signed multiplication correction
SIGMA             TMPD           SHIFT   RNI           ; shift {0, ProdU} by COUNTR to extract high result
SIGMA  -> eDX_AH                                       ; write high result
```

The `RESULT` register is used by both multiplication and division. For multiplication, it gets the higher `width` bits of TMPB, i.e. the lower half of product. `MULFIX` is the correction for signed multiplication on pseudocode line 8.

## Division

80386 uses the standard [non-restoring division algorithm](https://en.wikipedia.org/wiki/Division_algorithm#Non-restoring_division) for division. The dividend is {SIGMA,DIVTMP}, max 64 bits, while the divisor is TMPB, max 32 bits.

```c
1: do:                               // loop body is DIV7
2:     {SIGMA,DIVTMP} <<= 1;
3:     if (SIGMA < 0) SIGMA += TMPB;
4:     else           SIGMA -= TMPB;
5:     RESULT = (RESULT << 1) | (SIGMA >= 0 ? 1 : 0)
6:     COUNTR--;
7: while (COUNTR > 0)
8: if (SIGMA < 0) SIGMA += TMPB;     // DIV5
```

Let's look at one division routines (`DIV (F6.6)`) directly.

```asm
; DIV r
; Note: COUNTR = BITS_V (7/15/31), RPT executes COUNTR+1 iterations
eAX_AL -> DIVTMP  BITS_V         LDCNTR          ; DIVTMP = lower half of dividend, COUNTR=width-1
eDX_AH                           PASS            ; SIGMA = upper half of dividend
DSTREG -> TMPB                                   ; TMPB = divisor
SIGMA             TMPB            DIV7   RPT DLY ; All iterations here: dividend={SIGMA,DIVTMP}, divisor=TMPB
SIGMA             TMPB            DIV5           ; Final correction
SIGMA                            PASS            ; Preserve remainder through ALU
RESULT -> eAX_AL                         RNI     ; accumulator = quotient 
SIGMA  -> eDX_AH                                 ; upper-half reg = remainder
```

Here, DIV7 and DIV5 are single-cycle micro-ops. DIV7 encodes the whole loop body in the pseudo code (line 2-5, not including COUNTR decrement).  It updates SIGMA (remainder) and RESULT (quotient accumulator) and each iteration. Again RPT maintains the loop count and keeps the sequencer on the DIV7 micro-op. For division, there's no early-out so the loop executes for COUNTR+1 times. Finally DIV5 is the required finally correct for non-restoring division in pseudo-code line 8.

## Additional notes

One of the difficulties in figuring out the multiplication and division for the 80386 is the BITS_V constant. Its use in LDCNTR and the loop obviously points out its relation to the data width of the instruction, making 8/16/32 natural values for it, and RPT repeating COUNTR times. MUL and DIV work with that set up. However, the IDIV and AAM microcode repeatedly refuses to work. After many hours of debugging, I stumbled upon an unrelated routine in the microcode:

```asm
; PUSHAd
ESP               BITS_V         SUB         DLY      0    
SIGMA     INDSTK  -1             ADD             IN=+      
...
SIGMA  -> eSP                                DLY           
```

This finally gives the important hint that BITS_V could be `width-1` instead of `width`.  Here PUSHA pushes 8 registers to the stack. So SP should be subtracted by `8*2(16)` or `8*4(32)` bytes. The existance of `SIGMA-1` (SIGMA, -1, SUB) after `SIGMA=ESP-BITS_V` (ESP,BITS_V, SUB), clearly indicates that BITS_V is one less than 16 or 32.

Credit goes to reengine and dbalsom for providing the microcode, and Ken Shirriff for circuit level [reverse engineering of the 80386](https://www.righto.com/search/label/386). 