# Subsystem: firmware/ (RP2040 Bamboo Node Optical Transmitter)

`firmware/` executes on ARM Cortex-M0+ microcontrollers (Raspberry Pi Pico H / RP2040). It provides physical-layer optical modulation for an 850nm IR emitter FET driver in complete RF silence.

## Hardware Interface
* **Target MCU:** Raspberry Pi Pico H (RP2040, Dual ARM Cortex-M0+ @ 133MHz, 264kB SRAM).
* **Optical Emitter:** 850nm High-Power Infrared LED driven by a 2N7000 N-channel MOSFET on `GPIO 15`.
* **Timing & Baud Rate:** 1000 baud (1 ms per bit, 500 µs half-bit chip period) using dedicated hardware PIO (Programmable I/O) state machines or microsecond hardware timers.

## Production C vs. Bench MicroPython

The firmware subsystem is structured into two distinct execution tiers:

1. **Production Deployment (`firmware/src/`):**
   * Written in bare-metal **C99** and **RP2040 PIO assembly**.
   * Compiled via CMake and the Raspberry Pi Pico SDK into **`bamboo_node.uf2`**.
   * Emits pulses with **zero CPU overhead, nanosecond cycle-exact determinism, and zero dynamic memory allocation (`malloc`)**. Free of garbage collection pauses.
2. **Rapid Bench Prototyping (`firmware/python/`):**
   * Single-file **MicroPython** driver (`bamboo_transmitter.py`).
   * Designed for day-1 hardware breadboard validation and rapid iteration via [Thonny IDE](https://thonny.org).

---

## Directory & File Breakdown

### Root & Build Configuration
* **[`CMakeLists.txt`](file:///Users/mcamacho/git-repos/neuron-cupboard-core/firmware/CMakeLists.txt):** The CMake build blueprint. Directs the build system to locate the Raspberry Pi Pico SDK, assemble `src/manchester.pio` using `pioasm`, compile `src/main.c` and `src/manchester.c`, link hardware drivers (`hardware_gpio`, `hardware_pio`, `hardware_timer`), and generate the bootable `bamboo_node.uf2` binary. If `PICO_SDK_PATH` is absent, it automatically configures a host-side simulation target (`bamboo_node_sim`).
* **[`pico_sdk_import.cmake`](file:///Users/mcamacho/git-repos/neuron-cupboard-core/firmware/pico_sdk_import.cmake):** Standard Pico SDK bootstrap script for CMake environment integration.

### Source Files (`src/`) — Production Firmware
* **[`src/main.c`](file:///Users/mcamacho/git-repos/neuron-cupboard-core/firmware/src/main.c):** The microcontroller firmware entry point. Initializes GPIO 15, configures the Manchester transmitter context, and continuously broadcasts 10 Hz state beacon frames (`NEURON_MODE_FORMATION_LOCK`, `NEURON_LOCK_HARD_LOCKED`) over the optical link.
* **[`src/manchester.c`](file:///Users/mcamacho/git-repos/neuron-cupboard-core/firmware/src/manchester.c):** Deterministic Manchester encoder. Packs the 6-byte wire frame into 96 half-bit chips according to the IEEE 802.3 optical standard.
* **[`src/manchester.pio`](file:///Users/mcamacho/git-repos/neuron-cupboard-core/firmware/src/manchester.pio):** Hardware state machine assembly executed directly on the RP2040's Programmable I/O (PIO) blocks. Clocks out chips autonomously from the TX FIFO at 133 MHz.

### Headers (`include/`) — Internal Interfaces
* **[`include/manchester.h`](file:///Users/mcamacho/git-repos/neuron-cupboard-core/firmware/include/manchester.h):** Static transmitter context, timing constants, polarity enums, and frame-encoding function prototypes.
* **[`include/bamboo_pio.h`](file:///Users/mcamacho/git-repos/neuron-cupboard-core/firmware/include/bamboo_pio.h):** High-speed inline routine packing the 48-bit (96 chip) frame into exactly three 32-bit FIFO words for the RP2040 PIO engine.

### Verification (`test/`) — Host-Side Unit Tests
* **[`test/test_manchester.c`](file:///Users/mcamacho/git-repos/neuron-cupboard-core/firmware/test/test_manchester.c):** Host unit test compiled with standard `clang`/`gcc`. Validates IEEE 802.3 Manchester chip patterns, half-bit timing calculations, and frame assembly before flashing to silicon.
* **[`test/test_bamboo_pio.c`](file:///Users/mcamacho/git-repos/neuron-cupboard-core/firmware/test/test_bamboo_pio.c):** Host unit test proving 1-to-1 bitwise equality between the 3-word PIO FIFO packing and the 96-chip Manchester sequence.

### Bench Testing (`python/`) — MicroPython
* **[`python/bamboo_transmitter.py`](file:///Users/mcamacho/git-repos/neuron-cupboard-core/firmware/python/bamboo_transmitter.py):** Standalone MicroPython driver. Can be saved as `main.py` onto the Pico to test electrical breadboard continuity without needing the C cross-compilation toolchain.
