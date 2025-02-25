---
title: "UART in Verilog with Fractional Clock Dividers"
date: 2025-02-25T10:34:20+08:00
draft: false
sidebar: false
comment: true
author: nand2mario
---

Universal Asynchronous Receiver-Transmitter (UART) modules are basic components in embedded systems, enabling serial communication between devices. While there are many free implementations available online, a new challenge arose during my work on the independent software stack for the [Tang Console](https://sipeed.com/tangconsole): **non-integer clock multiples**. This issue surfaced when FPGA cores running on clocks of different frequencies need to communicate with an MCU via UART. Unlike SPI, where the master dictates the clock, UART demands both sides to adhere to a pre-agreed-upon baud rate (1Mbps in my case). Traditional integer clock dividers in this case yield imprecise baud rates and communication errors. In this post, I’ll explore a nice solution using a **fractional clock divider** technique.

<!--more-->

![UART](uart_timing_diagram.png)
{width="700"}

*Fig 1. UART frame timing requires precise baud rate alignment*

## The Challenge: Non-Integer Clock Divisions

Standard UART designs divide the system clock to produce a baud clock. For instance, a 100 MHz clock targeting 115,200 baud requires a divider of ~868.056. Integer dividers round this to 868 or 869, introducing a slight error. While manageable in many cases, this could introduce errors when the baudrate is closer to the system clock. For example, for a 21Mhz clock driving 2Mbps UART. The divider would be set at 11 cycles. That translates to 0.524us instead of 0.5us per bit. After 10 bits, the error would accumulate to `(0.524-0.5)*10=0.24us`, dangerously close to half a bit (0.25us). Actually testing showed that communication is not stable under this set up.

## Fractional Scaling

To solve this problem, it turns out that a useful trick is to use an **accumulator** that tracks fractional intervals using integer operations ([Bresenham's algorithm](https://en.wikipedia.org/wiki/Bresenham's_line_algorithm)). At each step, we:
1. Add the fractional denominator (`DIV_DEN`)
2. Check for overflow past the numerator (`DIV_NUM`)
3. Carry over the remainder when overflow occurs

This effectively approximates (with some jitters in the generated clock):
```
baud_clock_period = system_clock_period * (DIV_NUM / DIV_DEN)
```

The nice thing about this approach is that it avoids floating-point operations and multiplication entirely. In FPGA design, we typically avoid these due to their heavy resource demands and potential timing headaches. Instead, this solution relies solely on integer additions and comparisons, making it very efficient.

## Verilog Implementation

I implemented this in Verilog for both receiver and transmitter ([uart_rx.v](https://raw.githubusercontent.com/nand2mario/nestang/refs/heads/companion/src/sys/uart_rx.v), [uart_tx.v](https://raw.githubusercontent.com/nand2mario/nestang/refs/heads/companion/src/sys/uart_tx.v)). Here's a snippet from the receiver:

```verilog
// From uart_rx.v
reg [$clog2(DIV_NUM)-1:0] cnt;
always @(posedge clk) begin
    reg cnt_overflow;
    cnt_next = cnt + DIV_DEN;
    cnt_overflow = cnt_next >= DIV_NUM;
    if (state != 0) 
        cnt <= cnt_overflow ? cnt_next - DIV_NUM : cnt_next;
end
```

This mirrors the [video scaling logic](https://nand2mario.github.io/posts/2024/mdtang/) from my previous post:

```verilog
// From framebuffer.sv
xcnt_next = xcnt + width;  // Original width: 256 or 320
if (xcnt_next >= 960)      // Target width 960
    xcnt <= xcnt_next - 960;
```

Both shares the same idea:
1. **Accumulate** the fractional step (`DIV_DEN` or `width`)
2. **Detect overflow** against the target (`DIV_NUM` or `960`)
3. **Carry forward** the remainder

### The UART State Machine

The state machine largely resembles an integer-divider UART. For the receiver (RX):

1. **Idle**: Wait for start bit (RX line low)
2. **Start Bit**: Wait half a bit period for center alignment
3. **Data Bits**: Sample 8 bits at calculated intervals
4. **Stop Bit**: Validate frame end

```verilog
case (state)
    0: begin // Idle
        if (!rx) begin
            state <= 1;
            cnt <= 0;
            bit_index <= 0;
            rx_data <= 0;
        end
    end
    1: begin // Start bit, wait half a bit time
        if (cnt_next >= DIV_NUM/2) begin
            state <= 2;
            cnt <= 0;
        end 
    end
    2: begin // Data bits
        if (cnt_overflow) begin
            rx_data[bit_index] <= rx;
            if (bit_index == 7) 
                state <= 3;
            else 
                bit_index <= bit_index + 1;
        end
    end
    3: begin // Stop bit
        if (cnt_overflow) begin
            valid <= 1;
            data <= rx_data;
            state <= 0;
        end
    end
endcase
```

After detecting the start bit, we wait **half** a baud period to sample the first bit. This correctly hits the center of the baud clock period.

## Parameter Selection

Choose `DIV_NUM` and `DIV_DEN` such that,

    DIV_NUM / DIV_DEN  = clk_freq / baud_rate

For example, a 21.477 MHz clock targeting 1M baud could use `DIV_NUM=21477` and `DIV_DEN=1000`.

## Conclusion

By adopting a fractional clock divider technique inspired by Bresenham's algorithm, we've created a flexible UART implementation that supports arbitrary baud rates without specialized clock hardware. Compared with integer divider, there are several benefits. It supports exact baud rates regardless of clock relationship, uses only integer add/compare operations. Moreover the parameters allow runtime configuration.

The design is available as [uart_rx.v](https://raw.githubusercontent.com/nand2mario/nestang/refs/heads/companion/src/sys/uart_rx.v) and [uart_tx.v](https://raw.githubusercontent.com/nand2mario/nestang/refs/heads/companion/src/sys/uart_tx.v). 

Thanks for reading.

## Further Reading
1. [Bresenham's algorithm](https://en.wikipedia.org/wiki/Bresenham's_line_algorithm)
2. [UART protocol fundamentals](https://www.circuitbasics.com/basics-uart-communication/)
