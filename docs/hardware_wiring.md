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

## 2. Bill of Materials (BOM)

| Reference | Component | Recommended Part / Specs | Function / Rationale |
| :--- | :--- | :--- | :--- |
| **MCU** | Microcontroller | Raspberry Pi Pico (RP2040) | Dual Cortex-M0+ @ 133MHz with hardware PIO for jitter-free pulse generation |
| **SBC** | Edge Compute | Raspberry Pi 5 (4GB / 8GB) | Low-SWaP quad Cortex-A76 @ 2.4GHz with dual MIPI CSI-2 camera ports |
| **LED1** | 850nm IR Emitter | Vishay TSAL6100 / Osram SFH 4550 | $\lambda_p = 850\text{ nm}$, radiant intensity $> 130\text{ mW/sr}$, $V_F \approx 1.5\text{ V}$, $I_{\text{pulse}} \le 200\text{ mA}$ |
| **Q1** | Logic-Level MOSFET | IRLML2502 / AO3400A (SOT-23) or 2N7000 | N-Channel, $V_{DS} \ge 20\text{ V}$, $V_{GS(\text{th})} \le 1.2\text{ V}$, $R_{DS(\text{on})} \le 0.05\,\Omega$ @ 3.3V gate |
| **R_GATE** | Gate Resistor | $100\,\Omega$ ($\pm 1\%$, 1/8W) | Damps LC ringing on RP2040 GPIO 15 and protects MCU output stage |
| **R_PULL** | Gate Pulldown | $10\text{ k}\Omega$ ($\pm 5\%$, 1/8W) | Pulls gate to GND during microcontroller reset/boot; prevents spurious emissions |
| **R_LIMIT**| Current Limiter | $22\,\Omega$ (1W power rating, metal film) | Sets pulsed emitter current to ~150 mA from 5V rail |
| **CAM1** | Optical Sensor | Raspberry Pi Global Shutter Camera (Sony IMX296) or OV9281 | Monochrome sensor with global shutter to eliminate rolling-shutter pulse skew |
| **OPT1** | Optical Filter | 850nm Narrowband Bandpass (FWHM 15-20nm) | Blocks visible sunlight (400-750nm); isolates 850nm emitter against dark background |
| **PWR** | Power Rail | 5V DC BEC (from drone battery or USB-C PD) | Regulated 5.0V with shared common system ground |

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
                [R_LIMIT: 22 Ohm, 1W]
                 |
                 +
               ----- (Anode)
                \ /   850nm IR LED (TSAL6100)
                ---  (Cathode)
                 |
                 +-------------------+
                                     |
                                   +-+-+ (Drain)
  RP2040 GPIO 15 (Pin 20)          |   |
  ----+---[ R_GATE: 100 Ohm ]----->|   | Q1: IRLML2502 / AO3400A (N-Channel)
      |                            |   |
     [R_PULL: 10k]                 +-+-+ (Source)
      |                              |
  ----+------------------------------+
  GND (Pin 38 / System Ground)
```

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
