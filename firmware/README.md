# Subsystem: firmware/ (RP2040 Bamboo Node Optical Transmitter)

`firmware/` executes on ARM Cortex-M0+ microcontrollers (Raspberry Pi Pico / RP2040). It provides physical-layer optical modulation for an 850nm IR emitter FET driver in complete RF silence.

## Hardware Interface
* **Target MCU:** RP2040 (Dual ARM Cortex-M0+ @ 133MHz, 264kB SRAM).
* **Optical Emitter:** 850nm High-Power Infrared LED driven by N-channel MOSFET on `GPIO 15`.
* **Timing & Baud Rate:** Default 1000 baud (1 ms per bit, 500 µs half-bit chip period) using hardware timer interrupts or busy-delay loops.

## Encoding & Modulation
* **Physical Framing:** 6 bytes (48 bits / 96 Manchester chips) defined in [proto/neuron_wire.h](file:///Users/mcamacho/git-repos/neuron-cupboard-core/proto/neuron_wire.h).
* **Modulation:** IEEE 802.3 Manchester encoding:
  * Bit `0` $\rightarrow$ High-to-Low transition (`1, 0`)
  * Bit `1` $\rightarrow$ Low-to-High transition (`0, 1`)
* **Zero Allocation:** Static pre-allocated chip buffer (`MANCHESTER_MAX_CHIPS = 96`).

## Directory Layout
* `include/manchester.h`: Transmitter context and Manchester encoding API.
* `src/manchester.c`: Bounded-time pulse generation and frame assembly.
* `src/main.c`: RP2040 main entry point with periodic beacon broadcasting.
* `test/test_manchester.c`: Host-side unit test verifying bit patterns and CRC-8 integrity.
* `python/bamboo_transmitter.py`: MicroPython compatible driver for bench testing.
