# Bamboo Node: Physical Hardware Wiring & BOM Specification

## 1. System Architecture Overview

Each physical **Bamboo Node** payload consists of two primary tiers:
1. **Low-Level Transmitter Microcontroller:** Raspberry Pi Pico (RP2040) executing bare-metal C / PIO state machine to modulate the 850nm IR emitter.
2. **High-Level Compute Engine:** Raspberry Pi 5 single-board computer running the Panda Runtime (optical camera frame ingestion, spatial multi-tracking, consensus state machine, and Zenoh tactical gateway).

```
+-----------------------------------------------------------------------------------+
|                                 BAMBOO NODE                                       |
|                                                                                   |
|  +--------------------+     UART (115200 8N1)     +----------------------------+  |
|  | Raspberry Pi Pico  |<------------------------->| Raspberry Pi 5             |  |
|  | (RP2040 MCU)       |     TX(GP0) <-> RX(GPIO15)| (ARM Cortex-A76)           |  |
|  |                    |     RX(GP1) <-> TX(GPIO14)|                            |  |
|  +---------+----------+                           +--------------+-------------+  |
|            | GPIO 15 (PIO Out)                                   | CSI Ribbon     |
|            v                                                     v                |
|  +--------------------+                           +----------------------------+  |
|  | N-Channel MOSFET   |                           | Monochrome Global Shutter  |  |
|  | + 850nm IR LED     |                           | Camera + 850nm Bandpass    |  |
|  +--------------------+                           +----------------------------+  |
|            |                                                     ^                |
|            | 850nm Modulated Optical Photons                     |                |
+------------|-----------------------------------------------------|----------------+
             v                                                     |
             +============ Optical Line-of-Sight ==================+
```

---

## 2. Bill of Materials (BOM) & Bench Hardware Kit

### Bench Prototyping Kit (PiShop & Amazon Confirmed Orders)

| Component | Part / Item Description | Source | Status / Notes |
| :--- | :--- | :--- | :--- |
| **MCU** | Raspberry Pi Pico H (Pre-Soldered Male Headers) | PiShop.us | **Ordered.** Dual Cortex-M0+ @ 133MHz, hardware PIO bit-banging |
| **SBC** | Raspberry Pi 5 (4GB / 8GB) | Existing | **On-hand.** Host edge compute, executes Panda runtime & Zenoh gateway |
| **Camera** | Raspberry Pi Camera Module 3 NoIR (Standard 76° FOV) | PiShop.us | **Ordered.** Sony IMX708, NoIR filter allows 850nm light detection |
| **CSI Cable** | Pi 5 Camera Cable (200mm, 22-pin to 15-pin) | PiShop.us | **Ordered.** Adapts Pi 5 high-density 22-pin MIPI port to camera 15-pin |
| **Filter** | 12.5mm × 1.0mm 850nm Narrow Bandpass Filter Glass (2pcs) | Amazon | **Ordered.** Blocks 400–750nm ambient light; 12.5mm covers lens aperture |
| **IR LED** | Chanzon 5mm 850nm IR Emitter LEDs (100-pack) | Amazon | **Ordered.** $\lambda_p = 850\text{ nm}$, $V_F \approx 1.5\text{ V}$, 5mm through-hole breadboard legs |
| **MOSFET** | 2N7000 TO-92 N-Channel MOSFET 200mA 60V (100-pack) | Amazon | **Ordered.** Logic-level gate, 3-pin TO-92 package plugs into breadboard |
| **Resistors**| LuminologyPro 1000-pc 1/4W 25-Value Kit ($1\,\Omega$–$1\text{ M}\Omega$) | Amazon | **Ordered.** Includes $100\,\Omega$ (limiter/gate) & $10\text{ k}\Omega$ (pulldown) |
| **Breadboard**| 400-Point Solderless Prototyping Breadboard | PiShop.us | **Ordered.** Solderless platform for Pico H, FET, resistors, and LED |
| **Jumpers** | 40-pin Male-to-Female Jumpers (20cm) + Male-to-Male | PiShop / On-hand | **Ordered / On-hand.** Links Pico to Pi 5 GPIO header and ties breadboard rails |
| **USB Cable**| Micro-USB Data Cable | PiShop.us | **Ordered.** Pico firmware flashing, power, and serial monitoring |

### Electrical Component Reference

| Reference | Component | Recommended Part / Specs | Function / Rationale |
| :--- | :--- | :--- | :--- |
| **MCU** | Microcontroller | Raspberry Pi Pico H (RP2040) | Dual Cortex-M0+ @ 133MHz with hardware PIO for jitter-free pulse generation |
| **SBC** | Edge Compute | Raspberry Pi 5 (4GB / 8GB) | Low-SWaP quad Cortex-A76 @ 2.4GHz with dual MIPI CSI-2 camera ports |
| **LED1** | 850nm IR Emitter | Chanzon 5mm IR / Vishay TSAL6100 | $\lambda_p = 850\text{ nm}$, radiant intensity $> 130\text{ mW/sr}$, $V_F \approx 1.5\text{ V}$, $I_{\text{pulse}} \le 200\text{ mA}$ |
| **Q1** | Logic-Level MOSFET | 2N7000 (TO-92 through-hole) | N-Channel, $V_{DS} \ge 20\text{ V}$, logic gate compatible with 3.3V GPIO |
| **R_GATE** | Gate Resistor | $100\,\Omega$ ($\pm 1\%$, 1/4W) | Damps LC ringing on RP2040 GPIO 15 and protects MCU output stage |
| **R_PULL** | Gate Pulldown | $10\text{ k}\Omega$ ($\pm 5\%$, 1/4W) | Pulls gate to GND during MCU boot/reset; prevents spurious optical emissions |
| **R_LIMIT**| Current Limiter | $25\,\Omega$ (Four $100\,\Omega$ 1/4W in parallel = 1.0W) | Limits pulsed emitter current to ~140 mA from 5V VBUS rail |
| **CAM1** | Optical Sensor | Raspberry Pi Camera Module 3 NoIR | IMX708 sensor without IR cut filter; responsive to 850nm optical pulses |
| **OPT1** | Optical Filter | 12.5mm 850nm Narrowband Bandpass Disc | Blocks visible light (400-750nm); isolates 850nm emitter against dark background |
| **PWR** | Power Rail | 5V DC (Pico VBUS / Pi 5 Pin 2) | Regulated 5.0V with shared common system ground |

---

## 3. Transmitter Circuit Schematic & Math

### Emitter Current Limiting Calculation
* Supply Voltage ($V_{CC}$): $5.0\text{ V}$ (from Pico VBUS pin 40)
* LED Forward Voltage ($V_F$): $1.5\text{ V}$ (TSAL6100 typical @ 150mA)
* MOSFET Saturation Drop ($V_{DS(\text{on})}$): $I_D \times R_{DS(\text{on})} \approx 0.150\text{ A} \times 0.045\,\Omega \approx 0.007\text{ V} \approx 0\text{ V}$
* Target Peak Current ($I_{\text{peak}}$): $150\text{ mA}$ ($0.15\text{ A}$)

$$R_{\text{limit}} = \frac{V_{CC} - V_F - V_{DS(\text{on})}}{I_{\text{peak}}} = \frac{5.0 - 1.5 - 0.0}{0.150} = \frac{3.5}{0.150} = 23.33\,\Omega \approx 22\,\Omega$$

### Power Dissipation (50% Manchester Duty Cycle)
Because Manchester encoding enforces an exact 50% chip balance (transitions in every bit interval):
$$P_{\text{peak}} = I_{\text{peak}}^2 \cdot R_{\text{limit}} = (0.15)^2 \cdot 22 = 0.495\text{ W}$$
$$P_{\text{average}} = P_{\text{peak}} \times \text{DutyCycle} = 0.495 \times 0.5 = 0.248\text{ W}$$
*Selection:* A $22\,\Omega$ resistor rated for **1W** provides a $4\times$ thermal safety margin.  
*Breadboard Alternative:* Four $100\,\Omega$ standard 1/4W resistors wired in parallel equal $25\,\Omega$ rated for **1W** ($4 \times 0.25\text{ W}$), perfectly delivering ~140mA pulse current using common resistor assortment kits.

```
       +5V (VBUS / Pin 40)
           |
           +-----+
                 |
                [R_LIMIT: 25 Ohm (4x 100 Ohm in parallel, 1W)]
                 |
                 +
               ----- (Anode: Long Lead)
                \ /   850nm IR LED (Chanzon 5mm)
                ---  (Cathode: Short Lead)
                 |
                 +-------------------+
                                     |
                                   +-+-+ (Drain: Pin 3)
  RP2040 GPIO 15 (Pin 20)          |   |
  ----+---[ R_GATE: 100 Ohm ]----->|   | Q1: 2N7000 (TO-92 N-Channel)
      |                            |   |
     [R_PULL: 10k]                 +-+-+ (Source: Pin 1)
      |                              |
  ----+------------------------------+
  GND (Pin 38 / System Ground)
```

### Solderless Breadboard Layout Guide (400-Point Breadboard)

#### 1. 2N7000 MOSFET Pinout Identification
Looking directly at the **flat side** of the 2N7000 TO-92 package with the leads pointing downwards:
```
       +-------+
       | 2N7000|  <-- Flat face with writing
       +-------+
        |  |  |
        1  2  3
        |  |  |
     Source| Drain
          Gate
```
* **Pin 1 (Left):** Source $\rightarrow$ Connect to Breadboard **GND Blue Rail**.
* **Pin 2 (Center):** Gate $\rightarrow$ Connect to RP2040 GP15 via $100\,\Omega$ gate resistor; connect to **GND Blue Rail** via $10\text{ k}\Omega$ pulldown resistor.
* **Pin 3 (Right):** Drain $\rightarrow$ Connect to the **Cathode** (short lead) of the 850nm IR LED.

#### 2. 850nm IR LED Polarity
* **Long Lead (Anode +):** Connect to the current-limiting resistor bank.
* **Short Lead / Flat Edge on Lens Rim (Cathode -):** Connect to the 2N7000 Drain (Pin 3).

#### 3. Parallel Resistor Current Limiter Bank
* Take **four $100\,\Omega$ resistors** (Color band: Brown-Black-Black-Black or Brown-Black-Brown) from the resistor kit.
* Plug all four in parallel across two breadboard rows:
  - Row A: Connected to Pico Pin 40 (**VBUS**, 5V rail).
  - Row B: Connected to the **Anode** (long lead) of the 850nm IR LED.
* **Result:** Equivalent resistance = $25\,\Omega$, total power dissipation rating = $1.0\text{ W}$ ($4 \times 0.25\text{ W}$). No hot resistors, zero risk of component blowout.

#### 4. Filter Mounting
* Place the 12.5mm 850nm optical filter glass directly over the Camera Module 3 NoIR aperture.
* Hold gently in place around the outer rim with a small loop of non-marring tape or 3D printed lens shroud, ensuring the clear optical glass is unobstructed.

---

## 4. Raspberry Pi Pico to Raspberry Pi 5 Pinout

```
+------------------------------------+          +------------------------------------+
| Raspberry Pi Pico (Transmitter)    |          | Raspberry Pi 5 (Panda Compute)     |
| Pin #  | Label   | Purpose         |          | Pin #  | Label   | Purpose         |
+--------+---------+-----------------+          +--------+---------+-----------------+
| Pin 1  | UART0 TX| Telemetry Out   |--------->| Pin 10 | GPIO 15 | UART RX In      |
| Pin 2  | UART0 RX| Command In      |<---------| Pin 8  | GPIO 14 | UART TX Out     |
| Pin 3  | GND     | Common Ground   |==========| Pin 6  | GND     | Signal Ground   |
| Pin 20 | GP 15   | PIO Modulator   |          |        |         |                 |
| Pin 38 | GND     | Emitter Ground  |          | CSI-0  | 22-pin  | IMX296 Mono Cam |
| Pin 40 | VBUS    | 5V DC Power In  |<---------| Pin 2  | 5V DC   | 5V Power Supply |
+--------+---------+-----------------+          +--------+---------+-----------------+
```

> [!NOTE]
> On the Raspberry Pi 5, the MIPI camera connectors use a high-density 22-pin 0.5mm pitch flex ribbon. Ensure you use a 22-pin to 15-pin adapter cable when connecting traditional 15-pin camera modules (e.g. Raspberry Pi Global Shutter Camera).

---

## 5. Optical Filter & Lens Alignment

1. **850nm Bandpass Filter Mounting:**
   - Mount the 850nm bandpass filter directly inside the M12 lens mount or immediately in front of the lens barrel using black anodized filter step rings.
   - Light leaks around the filter perimeter will introduce visible background noise and degrade the signal-to-noise ratio (SNR).
2. **Camera Sensor Exposure Tuning:**
   - Configure sensor manual exposure to $\le 1000\,\mu\text{s}$ (1 ms) to freeze high-speed drone motion and eliminate optical bloom.
   - Lock analog gain to minimum ($1.0\times$) so that the background remains pure black ($0$ luminance) while the modulated emitter appears as a high-intensity isolated point source ($\ge 200$ luminance).

---

## 6. Bench Testing & Oscilloscope Verification

Before deploying onto a drone airframe, perform these hardware checks:

1. **Gate Switching Verification:**
   - Attach oscilloscope Channel 1 to **RP2040 GPIO 15** and Channel 2 to **Drain (Q1)**.
   - Run the bench transmitter: `python3 firmware/python/bamboo_transmitter.py`.
   - Verify that:
     - High level is $3.3\text{ V} \pm 0.1\text{ V}$.
     - Half-chip pulse width is exactly $500\,\mu\text{s} \pm 5\,\mu\text{s}$ (1000 baud Manchester rate).
     - Full 6-byte frame emits exactly 96 chips over 48 ms.
2. **Optical Emission Check:**
   - View the 850nm LED through a digital camera or smartphone sensor without an IR cut filter.
   - A distinct purple/white optical pulse sequence should be visible when transmitting.
3. **End-to-End Loopback:**
   - Point the filtered monochrome camera at the emitter from a distance of 1–5 meters.
   - Run `python3 -m panda.engine` to confirm zero-packet-loss decoding and bearing lock.
