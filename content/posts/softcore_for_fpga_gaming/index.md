---
title: "Adding a Softcore to SNESTang - part 1"
date: 2024-02-03T11:59:51+00:00
draft: false
sidebar: false
author: nand2mario
---

In the recently released [SNESTang 0.3](https://github.com/nand2mario/snestang/releases/tag/v0.3), a softcore-based I/O system is added to enhance the menu system and file system support. Let us explore how this works. Part one of the article discusses why the soft core is necessary, choice of CPU to use and how it works with the SDRAM.

<!--more--> 

A bit of background first. My FPGA cores, NESTang and SNESTang, used to be completely standalone, with everything written in Verilog. This helped keep things simple, easy to install and update for the enduser, which are one of the  goals of the projects. However, there are functions that are much easier to implement using a CPU rather than a hardware description language, like USB controllers, menu system, file systems, etc. Projects like MiSTer and MIST use separate ARM processors to handle these tasks. MiSTer even runs a full Linux OS on the ARM. Unfortunately the Sipeed Tang FPGA boards that NESTang/SNESTang run on do not have a processor chip for this purpose (at least not one that is currently available for developers to use). For this reason, we have resorted to implementing things like FAT32 with Verilog. Although they work, the downside is that as we add more of these I/O features, they take up precious FPGA logic space, which should be used for game logic.

Introducing a softcore CPU could solve these problems, as all these I/O functionality, no matter how complex, could then be implemented with firmware that does not take FPGA space. But there is one major challenge: softcore memory space. Most FPGA softcore examples use FPGA block RAM for softcore memory. Unfortunately for our case, block RAM is in short supply. The Tang Primer 25K only has 126KB of block RAM, 90% of which is already used by the core itself. The remaining 10% is not enough. There is also the other problem of where to put the program. Most examples just store the program in HDL arrays or block RAM. So we are back to either taking up logic space or BRAM space again.

Our solution is to use **SDRAM for softcore main memory**, and store the **firmware program in bitstream SPI flash memory**. It turns out to be working great, and is also relatively easy to use for the enduser. There is no need for extra addon boards or hard-to-use software tools involved.

As for the softcore itself, [PicoRV32](https://github.com/YosysHQ/picorv32) is chosen for its small size and easy-to-control memory interface. The core runs in RV32I mode with no interrupt support. Total area of the softcore plus SD, OSD and UART is about 2000 LUTs, smaller than the previous Verilog SD implementation. I also experimented with the excellent [FemtoRV32](https://github.com/BrunoLevy/learn-fpga/tree/master/FemtoRV) by Bruno Levy. It was also very helpful. 

Here are the more in-depth details.

## SDRAM to the rescue

SDRAM would be a nice place to put the softcore memory. Basically all retro-gaming oriented FPGA boards have it, including the Tang boards. They are also spacious compared to FPGA block RAM. Here two 32MB SDRAM chips are available to us. A few MB will probably be enough for our firmware for the foreseeable future. The only problem left is that we need a way to **share the SDRAM between the gaming core and softcore CPU**. So down the rabbit hole we go...

Our SDRAM is 16-bit wide, with 32MB of total space divided into 4 banks. As described in [SNESTang design notes](https://github.com/nand2mario/snestang/blob/main/doc/design.md), the SDRAM controller that we wrote for the SNES core provides two access channels (or "ports"). Channel 0 is for everything S-CPU (SNES CPU), the cartridge ROM, WRAM and BSRAM. Channel 1 is for the ARAM of S-SMP (the audio processor). These two channels work in parallel and are implemented with SDRAM bank interleaving. This way, they appear to the S-CPU and S-SMP as separate memory chips, as in the original SNES hardware. SDRAM runs at 6x main logic clock speed, with the following fixed sequence of operations.

```
fclk_#    CPU         ARAM
   0      RAS1    
   1      CAS1        DATA2
   2                  RAS2/Refresh
   3                  
   4      DATA1       CAS2
   5                  
```

A memory access begins with a RAS (row activation) SDRAM command, followed by CAS (column activate). Finally memory sends back DATA, if it is a read. Note how accesses from the two channels overlap ("interleave") with each other. This works because they access different banks of the chip. The row/column addresses and data are registered by the memory's per-bank circuitry during the accesses.

Now we need to add softcore accesses to the (already busy) mix. One way we can do this is to add more bank interleaving. We actually already have plans to add another channel for the SNES core to use. So in total that would mean we use all four banks and provide four channels of access. The main issue with interleaving many banks, is it requires high memory clock speed, which tends to make things unstable. I played with the 4-channel idea and came up with several sequencing schemes. Unfortunately, none of them works for me reliably. So I was kinda stuck.

If we look at our problem carefully, however, one property we can exploit is that the softcore does not have tight timing requirements like the SNES core. It is fine if a softcore CPU instruction is delayed for a few cycles. So one idea is to let it *tag along* with one of the existing channels, i.e. share access with a lower priority. As long as the existing channel is not 100% full, the softcore will run ok, although a bit more slowly. So that is the final solution. The new access sequences look like this,

```
        Normal schedule         Delayed write
fclk_#  CPU/RV  ARAM  3rd       CPU/RV  ARAM  3rd
 0      RAS                     RAS           
 1              RAS                            
 2      CAS                     READ              
 3              CAS                     RAS         
 4                         
 5      DATA                    DATA                  
 6              DATA                    WRITE
 7                                 
```

First of all, the access sequence is longer at 8 cycles as we already included slots for a 3rd channel (not in use yet). That means memory is now running at 86.4Mhz (8*10.8Mhz). I have not been able to use the memory at over 100Mhz. So this is close to our limit. Second, there are two schedules ("normal" and "delayed write") for the accesses. I will not go into details why this is necessary as it has more to do with allowing three channels than sharing the first channel. It suffices to say that SDRAM timing is kinda tricky and details are buried deep in the datasheets...

Back to the main topic, the low priority access of the softcore is implemented with something like this,

```verilog
module sdram_snes(
    ...
    input      [22:1] rv_addr,
    input             rv_rd,
    input             rv_wr,
    output reg        rv_wait,   // Softcore request is not serviced this cycle
    ...
);

always @(posedge fclk) begin
    ...
    if (cycle[0]) begin
        if (cpu_rd | cpu_wr) begin
            ...                 // RAS for cpu access
            rv_wait <= 1;
        end else if (rv_rd | rv_wr) begin
            ...                 // RAS for softcore access
            rv_wait <= 0;
        end
    end
    ...
end
```

Basically we added an extra output `rv_wait`, which becomes high whenever the RV softcore is preempted by the SNES CPU for memory accesses. This signal is then sent to PicoRV32's memory interface, instructing it to keep trying the memory access until it finally succeeds.

How big of a performance impact does this bring? Directory loading in the menu when a game is running is slightly slower. That is all I can notice. So I would say this is a good solution. It is scalable enough to allow up to 8MB of memory space (one bank of the SDRAM) for the softcore. It is also quite general. For other gaming cores, as long as there is one SDRAM channel that is not 100% utilized, we can attach the softcore to it.

<!-- ![](menu_dir.jpg) -->

In the next part of this article. We will discuss where the firmware program is stored and how the softcore boot process works.

Continue to [part 2](../softcore_for_fpga_gaming_part_2).