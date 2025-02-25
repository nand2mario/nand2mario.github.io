---
title: "UART in Verilog with Fractional Clock Dividers"
date: 2025-02-25T10:34:20+08:00
draft: false
sidebar: false
comment: true
author: nand2mario
---


Universal Asynchronous Receiver-Transmitter (UART) modules are a cornerstone of embedded systems, facilitating serial communication between devices. While free UART implementations abound online, I encountered a unique challenge while developing an independent software stack for the Tang Console: non-integer clock multiples. This issue surfaced when FPGA cores, running on clocks of varying frequencies, needed to communicate with an MCU via UART. Unlike SPI, where the master dictates the clock, UART demands both sides align to a fixed baud rate. Traditional integer clock dividers often yield imprecise baud rates or force unnecessarily slow speeds. In this post, I’ll walk through a more elegant fix: a fractional clock divider technique, inspired by a video scaling trick I covered here.

<!--more-->

UART Timing Diagram
Fig 1. UART frame timing hinges on precise baud rate alignment
{width="700"}
The Challenge: Non-Integer Clock Divisions
Standard UART designs divide the system clock to produce a baud clock. For instance, a 100 MHz clock targeting 115,200 baud requires a divider of approximately 868.056. Integer dividers round this to 868 or 869, introducing a slight error. While this is tolerable in many scenarios, applications demanding tight precision—like the Tang Console—suffer.
The Fix: Fractional Clock Dividers
Borrowing from Graphics: Fractional Scaling
The solution lies in an accumulator-based approach, tracking fractional intervals with integer math—a nod to Bresenham's algorithm. Here’s the process:
Add the fractional denominator (DIV_DEN) at each step.
Check if the accumulator exceeds the numerator (DIV_NUM).
Subtract DIV_NUM on overflow, carrying forward the remainder.
This effectively approximates:  
baud_clock_period = system_clock_period * (DIV_NUM / DIV_DEN)
Verilog in Action
We implemented this in Verilog for both receiver and transmitter (uart_rx.v, uart_tx.v). Here’s a snippet from the receiver:
verilog
// From uart_rx.v
reg [$clog2(DIV_NUM)-1:0] cnt;
always @(posedge clk) begin
    reg cnt_overflow;
    cnt_next = cnt + DIV_DEN;
    cnt_overflow = cnt_next >= DIV_NUM;
    if (state != 0)
        cnt <= cnt_overflow ? cnt_next - DIV_NUM : cnt_next;
end
This mirrors the video scaling logic from my earlier post (framebuffer.sv):
verilog
// From framebuffer.sv
xcnt_next = xcnt + width;  // Original width: 256 or 320
if (xcnt_next >= 960)      // Target width: 960
    xcnt <= xcnt_next - 960;
Both share the same core idea:  
Accumulate the step size (DIV_DEN or width).  
Detect overflow against the target (DIV_NUM or 960).  
Carry forward the remainder.
The UART State Machine
The state machine largely resembles a classic integer-divider UART. For the receiver (RX):
Idle: Await a low RX line (start bit).
Start Bit: Wait half a bit period to align with the center.
Data Bits: Sample 8 bits at calculated intervals.
Stop Bit: Confirm the frame’s end.
verilog
case (state)
    0: if (!rx) begin  // Start bit detection
        state <= 1;
        cnt <= 0;
    end
    1: if (cnt_next >= DIV_NUM/2) begin  // Center-align
        state <= 2;
        cnt <= 0;
    end
    2: if (cnt_overflow) begin  // Data bit sampling
        rx_data[bit_index] <= rx;
        bit_index <= bit_index + 1;
    end
    3: if (cnt_overflow) valid <= 1;  // Stop bit
endcase
After detecting the start bit, we wait half a baud period to sample at the bit’s center, ensuring accuracy.
Picking Parameters
Select DIV_NUM and DIV_DEN to satisfy:  
DIV_NUM / DIV_DEN = clk_freq / baud_rate
For example, a 21.477 MHz clock targeting 1M baud could use DIV_NUM = 21477 and DIV_DEN = 1000.
Why It Works
This fractional divider, rooted in Bresenham’s algorithm, delivers a flexible UART that nails arbitrary baud rates without exotic clock hardware. It’s a testament to how graphics algorithms can breathe new life into hardware design. Compared to integer dividers, it offers:  
Precision: Exact baud rates, regardless of clock ratios.  
Simplicity: Relies solely on integer addition and comparison.  
Flexibility: Runtime-configurable parameters.
The full code is available in uart_rx.v and uart_tx.v.
Wrapping Up
This fractional clock divider technique solves a tricky UART problem with elegance and efficiency. It’s a small but powerful example of cross-domain inspiration in engineering. Thanks for reading!
Dive Deeper
Bresenham's Algorithm  
UART Protocol Basics
Key Changes:
Title: Made it punchier and more descriptive.
Intro: Streamlined the problem setup and hook.
Clarity: Simplified explanations (e.g., accumulator logic) without losing depth.
Code Context: Tied Verilog snippets more tightly to their purpose.
Conclusion: Emphasized benefits concisely and added a reflective note.
Formatting: Improved headings, tightened lists, and ensured consistent terminology (e.g., "baud clock period").
Tone: Kept it conversational yet authoritative, avoiding overly dense jargon.
Let me know if you’d like further tweaks!