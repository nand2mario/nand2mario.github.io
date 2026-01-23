---
title: "Projects"
---

Open source FPGA projects for retro gaming and computing.

## FPGA Gaming Cores

Complete console implementations for Sipeed Tang FPGA boards.

* [NESTang](https://github.com/nand2mario/nestang) - Nintendo Entertainment System for Tang Primer 25K, Nano 20K and Primer 20K. My first FPGA gaming project.
* [SNESTang](https://github.com/nand2mario/snestang) - Super Nintendo Entertainment System for Tang FPGAs. Features a RISC-V softcore for menu system.
* [TangCore](https://github.com/nand2mario/tangcore) - Unified FPGA gaming distribution for Tang boards. Includes NES, SNES, GBA, Genesis and SMS cores with easy core switching.
* [GBATang](https://github.com/nand2mario/gbatang) - Game Boy Advance for Sipeed Tang boards.
* [MDTang](https://github.com/nand2mario/mdtang) - Sega Mega Drive / Genesis for Tang boards.
* [NanoSPC](https://github.com/nand2mario/nanospc) - SNES SPC music player for Tang Nano 20K.
* [SMSTang](https://github.com/nand2mario/smstang) - Sega Master System for Tang FPGAs.

## x86 CPU Cores

FPGA implementations of classic Intel processors.

* [486Tang](https://github.com/nand2mario/486tang) - 80486 on the Sipeed Tang Console 138K. First ao486 port to non-Altera FPGA.
* [z8086](https://github.com/nand2mario/z8086) - 8086 FPGA core running the original Intel microcode.
* [z86](https://github.com/nand2mario/z86) - A pipelined 80286-class FPGA softcore CPU. *(Incomplete)*
* [ao486-sim](https://github.com/nand2mario/ao486-sim) - Educational whole-system simulation of the ao486 CPU core and PC architecture.
* [8086 Microcode Browser](/8086_microcode.html) - Interactive Intel 8086 microcode viewer.

## USB & Interfaces

* [usb_hid_host](https://github.com/nand2mario/usb_hid_host) - Compact USB HID host FPGA core supporting keyboards, mice and gamepads. Pure Verilog, no CPU needed.
* [usb_host_pmod](https://github.com/nand2mario/usb_host_pmod) - Dual-socket USB host PMOD module hardware design.

## Memory Controllers

* [DDR3 controller for Tang Primer 20K](https://github.com/nand2mario/ddr3-tang-primer-20k) - DDR3-800 controller with low latency for Gowin GW2A-18C.
* [SDRAM controller for Tang Nano 20K](https://github.com/nand2mario/sdram-tang-nano-20k) - Simple SDRAM controller with example code. Great starting point.
* [DDR3 Frame Buffer](https://github.com/nand2mario/ddr3_framebuffer_gowin) - DDR3 frame buffer in Verilog for Gowin FPGA.

## Other

* [3dfx Voodoo Demos](https://github.com/nand2mario/3dfx_voodoo_demos) - Self-contained 3dfx Voodoo 1 (SST-1) demos on Mac/Linux.
* [Dieshots](https://github.com/nand2mario/dieshots) - High-resolution processor die photographs.
