---
title: "Making USB HID hosting easy for FPGA projects"
date: 2023-08-29T11:59:51+08:00
draft: true
sidebar: false
---

A while ago I came across [hi631's work](https://qiita.com/hi631/items/4f263ca676e4be14b9f8) on adapting the very old ukp (USB keyboard processor) design to support USB gamepads on FPGAs. I ported that to [NESTang](https://github.com/nand2mario/nestang) and it worked well. Here I look at whether we can further extend it to support more devices, i.e. keyboards, mice and gamepads.

First a bit of background. A hurdle I have encountered multiple times while working on FPGA projects is dealing with USB devices. Many projects require support for I/O devices such as keyboards, mice, joysticks (Human Interface Devices in USB terms). While it may seem straightforward, USB is unfortunately a technology that relies on software control, particularly on the host side. Therefore, unless the FPGA being used is a System-on-Chip (SoC) with an ARM CPU (like the one in [MiSTer](https://misterfpga.org/)), supporting USB HID devices is not a simple task. As a result, various smaller projects often opt for hard-to-find [PS/2 keyboards](https://www.instructables.com/PS2-Keyboard-for-FPGA/). [MIST](http://www.harbaum.org/till/mist/mist.html) has a dedicated ARM SoC ("IO controller") that handles USB I/O and other related operations.

So the goal is to create a reusable Verilog module that supports common keyboards, mice and gamepads, requires little hardware support, and uses low amount of FPGA resource.

The result is QuickUSB. It is tested on Sipeed Tang Nano 20K, and uses xxx LUTS, xxx registers and xxx BRAM.

## Architecture

## Detecting Devices

## Parsing HID Reports

## The Demo Project

