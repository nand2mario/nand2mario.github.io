---
title: "New Architecture for Tang Console"
date: 2025-03-10T12:30:20+08:00
draft: true
sidebar: false
comment: true
author: nand2mario
---

A year ago, I [added a softcore CPU to SNESTang](/posts/softcore_for_fpga_gaming), to make FPGA gaming cores easier to use. Over the past months, this allowed me to implement features like an improved menu system and core switching. While the softcore served its purpose, its limitations—slow performance, inability to handle complex peripherals like USB, and FPGA resource consumption—became apparent. Now is again the time to introduce some changes. After extensive collaboration with the Sipeed team, we've finally found a way to tap the Tang boards' onboard MCU (a Bouffalo BL616 chip) to address these challenges. The result is **[TangCore 0.6](https://github.com/nand2mario/tangcore/releases/tag/r0.6)**, along with all four gaming cores. In this post, I'll discuss integrating the MCU with the Tang gaming cores.

## Tapping the Onboard MCU 

**Why Use an MCU?**
As explained in my [softcore post](/posts/softcore_for_fpga_gaming), combining a CPU with an FPGA is a common design pattern for balancing performance and flexibility. The Tang series boards include a [Bouffalo BL616](https://en.bouffalolab.com/product/), a RISC-V MCU comparable to the ESP32. Originally used as a USB-JTAG/UART bridge for FPGA programming, the BL616’s capabilities were underutilized. Projects like [FPGA-Companion](https://github.com/harbaum/FPGA-Companion) have been trying to use the chip. However, developers (and I believe Sipeed) have yet to find a straightforward way to combine the official and custom firmware, and not bricking users' boards. So FPGA-Companion suggests using a separate board with BL616 (Sipeed M0S) and not flashing the on-board BL616, complicating the user's setup.

**A New Solution.**
A way to solve the problem surfaced in the last month after much discussion I had with the Sipeed team. Sipeed would upgraded their BL616 firmware to enable dual-mode operation,

1. **PC Connected**: The BL616 acts as a standard JTAG/UART bridge, if it detects connection to a PC.
2. **Standalone Mode**: The MCU runs custom TangCore firmware from a predefined flash address.

This approach preserves the board’s core functionality while enabling custom firmware. Users can now flash TangCore firmware seamlessly—no extra hardware needed.  

## Proper USB Support
Normally when you connect the FPGA board to PC, it is a "USB Device". However, BL616 has the ability to behave as "USB Host", where it manages other devices. This is very useful to us as we can then use USB gamepads, USB receiver for controllers and etc. The only issue here, is that we need to provide power to the connected device (or devices, if we use a hub). The Tang boards currently lack the circuitry to provide power through USB (except the USB-A host port on Tang Mega). After some experiments, I found a way out by using a "USB OTG dongle" with "power pass-through" (see [installation guide](https://nand2mario.github.io/tangcore/user-guide/installation/) for details). These are normally used for cell-phones to connect USB drives, while charging the phone at the same time. Perfect for us.

The actual USB support is provided by the [CherryUSB](https://github.com/cherry-embedded/CherryUSB) stack. Currently USB MSC (usbdrives) and HID (HID gamepads) classes are implemented. Support for the more popular XInput gamepads is in development. CherryUSB requires a multi-tasking environment, in this case FreeRTOS, as USB is inherently multi-tasking (you can have many devices and transfers going on at the same time). So FreeRTOS is added to the firmware too. Here we see the productivity of combining a performant MCU and mature software stack - basic USB support was functioning after two days of work. BL616 has enough performance and ability to support all this well. For USB drive, we again use the excellent FatFS library, supporting FAT32 and even exFAT file systems.

## Fast JTAG Programming

Now that the MCU is running and accessing peripherals like USB well, it needs to tend to the other main task on hand - managing the FPGA chip. There are at least two things it needs to do: to load game cores on the FPGA, and load ROMs to the running game cores.

I borrowed the bit-bang JTAG programming logic from openFPGALoader. Here's the main function (simplified a bit for illustration) to load the bits.

```c
static int jtag_writeTDI(const uint8_t *tx, uint8_t *rx, int len) {
	for (uint32_t i = 0; i < len; i++) {
		if (tx)
			tdi = (tx[i >> 3] & (1 << (i & 7))) ? 1 : 0;
        if (tdi) GPIO_PIN_JTAG_TDI_H(); else GPIO_PIN_JTAG_TDI_L();     // send TDI
        GPIO_PIN_JTAG_TCK_L();                                          // low  TCK 
        if (tdi) GPIO_PIN_JTAG_TDI_H(); else GPIO_PIN_JTAG_TDI_L();     // send TDI
        GPIO_PIN_JTAG_TCK_H();                                          // high TCK
	}
	return len;
}
```

Essentially the JTAG bus includes 4 pins: TCK, TMS, TDI, TDO. Signals get registers on rising edge of the clock TCK. TMS controls the state (with a fancy [TAP state machine](https://www.allaboutcircuits.com/technical-articles/jtag-test-access-port-tap-state-machine/)), and TDI transfers the actual data to the circuit (the FPGA), while TDO is data coming out of the circuit. So what's happening here in the code, is that it's bit-banging the data bits by setting the TDI GPIO pin, and then toggling the clock, first low and then high. So with that we can transfer the ~2MB bitstream to the FPGA. Of course I skipped over details on how to send commands to the FPGA so that it enters the configuration state, and etc. But you get the idea.

However, the above code is not fast enough. It took about 13 seconds to load a core. Now's the time to exercise my optimization chops... After going through the [BL616 reference manual](https://github.com/bouffalolab/bl_docs/tree/main/BL616_RM) about the GPIO registers and some experimentation, it was discovered that switching the GPIO to "direct output mode" (instead of the default "set/clear mode") and inlining/unrolling the bit operations sped up this by over 4 times. Finally we are able to load a new core in ~2 seconds.

Here's the optimized inner-loop that does the trick.

```c
void jtag_writeTDI_msb_first_gpio_out_mode(const uint8_t *tx, int bytes, bool end) {
	for (int i = 0; i < bytes; i++) {
		uint8_t byte = tx[i];
		// bit 7
		*reg_gpio0_31 = (byte & 0x80) >> 4;           // bit 3 (TDI) = data, bit 1 (TCK) = 0
		*reg_gpio0_31 = ((byte & 0x80) >> 4) | 2;     // bit 3 (TDI) = data, bit 1 (TCK) = 1
		// bit 6
		*reg_gpio0_31 = (byte & 0x40) >> 3;     
		*reg_gpio0_31 = ((byte & 0x40) >> 3) | 2; 
		// bit 5
		*reg_gpio0_31 = (byte & 0x20) >> 2;     
		*reg_gpio0_31 = ((byte & 0x20) >> 2) | 2; 
		// bit 4
		*reg_gpio0_31 = (byte & 0x10) >> 1;     
		*reg_gpio0_31 = ((byte & 0x10) >> 1) | 2; 
		// bit 3
		*reg_gpio0_31 = (byte & 0x8);     
		*reg_gpio0_31 = (byte & 0x8) | 2; 
		// bit 2
		*reg_gpio0_31 = (byte & 0x4) << 1;     
		*reg_gpio0_31 = ((byte & 0x4) << 1) | 2; 
		// bit 1
		*reg_gpio0_31 = (byte & 0x2) << 2;     
		*reg_gpio0_31 = ((byte & 0x2) << 2) | 2; 
		// bit 0
		*reg_gpio0_31 = ((byte & 0x1) << 3) | (i == bytes-1 && end);  	// TMS=1 if at the end
		*reg_gpio0_31 = ((byte & 0x1) << 3) | 2 | (i == bytes-1 && end);	// TMS=1 if at the end
	}
}
```

## MCU-FPGA communication

After the core is successfully loaded. We need two-way communication between the MCU and the FPGA for things like rom loading, gamepad updates and overlay display updates.

The communication line is currently a 2Mbps UART between BL616 and FPGA. Getting UART to run at high speed, given the various FPGA clocking conditions is actually non-trivial. I wrote about  [UART with fractional clock divider](/posts/2025/uart_with_fractional_clock_divider) while working on this. The BL616 is actually able to do >= 10Mbps UART. So I may optimize this further in the future.

Here are the types of data exchanged between the MCU and FPGA (see end of [this](https://nand2mario.github.io/tangcore/dev-guide/core-debugging/#monitor-mcu-fpga-communcation) for the protocol).

* **Overlay display** (MCU to FPGA). Here the MCU uses the FPGA as a text display. In overlay (menu) mode, whenver the MCU wants to display something, it sends the text (along with screen location) to be displayed to the FPGA through UART. Every core, including the initial empty "monitor" core, contains a 32x28 text display buffer that gets updated with these commands, and shows the text on-screen.
* **Controller updates** (MCU and FPGA two-way). DS2/SNES controllers are connected to the FPGA. USB controllers are connected the MCU. So a few commands let the MCU and FPGA exchange controller updates in both ways. Then the MCU uses these two control the menu, while the FPGA uses these for game controls. Currently the FPGA sends gamepad updates to MCU every 20ms.
* **ROM loading** (MCU to FPGA). This is just a blob of binary bits from the MCU to FPGA.

At least two things are missing now,

* **Load/store support**. There's currently no SRAM/cartridge RAM load/store, or savestate load/store. These will be implement down the line.
* **Core configuration**. A scheme similar to [MiSTer's configuration strings](https://mister-devel.github.io/MkDocs_MiSTer/developer/conf_str/) should be implemented. So that a per-core menu can be shown for configuration of core functionality.

## Conclusions - BL616 strengths and weaknesses

Strengths:

* High performance SoC MCU with 320Mhz 32-bit risc-v CPU
* Comprehensive on-chip peripherals - DMA, USB, Wifi, BLE and more.
* Low cost.

Weaknesses:

* Still not as performant as the AP-level CPU on DE10-nano (A9), or Zynq (A53).
* MCU-FPGA speed is not as fast as DE10-nano or Zynq, as those are in the same chip. For example, for DE10-nano the HPS and FPGA fabric have shared access to the hardened DDR3 controller, which MiSTer took adavantage of to provide a high-resolution framebuffer, saving a lot of FPGA resource.

Overally, BL616+FPGA is a much better architecture than the softcore-based approach of last year. Hopefully this round of infrastructure work will allow the Tang gaming cores to develop better and faster. FPGA gaming has been a fun and learning hobby. Thanks to Sipeed for brainstorming and developing together. 

Happy gaming and happy hacking.

