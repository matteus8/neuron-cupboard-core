# Bamboo Node: Hardware Procurement & Bench Bringup Guide

The complete software stack (wire codecs, PIO transmitter firmware, dual-aperture vision, SDMA spatial multi-tracking, consensus engine, and tactical Zenoh gateway) is fully implemented, verified with 27 unit/fuzz tests, and audited by SAST.

When you are ready to transition from software simulation to physical hardware testing, this guide provides the exact components to order and the desktop bench verification sequence.

---

## 1. Procurement Status & Sourcing Checklist

### ✅ Order 1: PiShop.us (ORDER PLACED)
| Component | Item Ordered | Purpose | Status |
| :--- | :--- | :--- | :---: |
| **Microcontroller** | Raspberry Pi Pico H (Pre-Soldered Headers) | Zero-jitter Manchester PIO pulse generator | Ordered |
| **Prototyping** | Half-size 400-Pin DIY Solderless Breadboard | Circuit mounting without soldering | Ordered |
| **USB Link** | USB-A to Micro-USB-B cable (45cm) | Pico programming and telemetry link | Ordered |
| **Camera Sensor** | Raspberry Pi Camera Module 3 NoIR | 850nm optical receiver with autofocus | Ordered |
| **Pi 5 Cable** | Camera Cable for Raspberry Pi 5 (200mm, 22-to-15 pin) | Connects camera to Raspberry Pi 5 CAM0 | Ordered |
| **Wiring** | Male-to-Female Jumper Cables × 40 (20cm) | Connects Raspberry Pi 5 GPIO to breadboard | Ordered |

---

### 🛒 Order 2: Amazon Checklist (FINAL PARTS NEEDED)

You only need **4 small electronics items** from Amazon to complete the testbed:

| Component | Exact Amazon Search Query | Description / Notes | Approx. Cost |
| :--- | :--- | :--- | :--- |
| **1. Optical Filter** | `850nm narrow bandpass optical filter` | 12mm, 15mm, or 25mm circular glass disc (FWHM 15–20nm). Placed in front of Camera Module 3 to block room light. | ~$14.00 |
| **2. 850nm IR LEDs** | `Vishay TSAL6100 850nm IR LED` *(or `850nm 5mm high power IR LED 10 pack`)* | 5mm through-hole infrared emitter with radiant intensity $>130\,\text{mW/sr}$. | ~$5.00 |
| **3. Switching FET** | `2N7000 N-channel MOSFET TO-92` | 3-pin through-hole transistor switching the 5V LED rail. | ~$5.00 |
| **4. Resistors** | `electronic resistor assortment kit 1/4w` | Contains standard $100\,\Omega$ (gate) and $10\text{ k}\Omega$ (pulldown) resistors. | ~$7.00 |

> [!TIP]
> **Breadboard EE Trick for the 1W Power Resistor:**  
> Instead of buying a special bulky 1W resistor, your 1/4W resistor kit already has what you need! Putting **four $100\,\Omega$ 1/4W resistors in parallel** on the breadboard yields an equivalent $25\,\Omega$ resistance rated for **1W** ($4 \times 0.25\text{ W}$), perfectly setting the ~140mA emitter pulse current!
>
> *(Optional)* If your existing male-to-male jumper wires at home feel loose, search: `solderless breadboard jumper wire kit preformed` (~$6.00) for rigid U-shaped solid-core copper wires that never pop out.

---

## 2. Desktop Bench Assembly Steps

Follow the circuit diagram in [`docs/hardware_wiring.md`](file:///Users/mcamacho/git-repos/neuron-cupboard-core/docs/hardware_wiring.md#L45-L82):

```
       +5V (Pico Pin 40 / VBUS)
           |
          [R_LIMIT: 22 Ohm, 1W]
           |
         ----- (Anode)
          \ /   850nm IR LED (TSAL6100)
          ---  (Cathode)
           |
           +-------------------+
                               |
                             +-+-+ (Drain)
  RP2040 GPIO 15 (Pin 20)    |   |
  ----+---[ R_GATE: 100R ]-->|   | Q1: 2N7000 / IRLML2502 (N-Channel)
      |                      |   |
     [R_PULL: 10k]           +-+-+ (Source)
      |                        |
  ----+------------------------+
  GND (Pico Pin 38)
```

---

## 3. Four-Step Bench Bringup Workflow

Once your components arrive, you can bring up the physical transceiver payload using our built-in diagnostic tool [`scripts/bench_tool.py`](file:///Users/mcamacho/git-repos/neuron-cupboard-core/scripts/bench_tool.py):

### Step 1: Discover Devices
Plug the Raspberry Pi Pico into your computer via USB:
```bash
python3 scripts/bench_tool.py --mode=scan
```
*Expected Output:*
```
[+] Microcontroller Serial Interfaces (RP2040 / Pico):
  -> /dev/tty.usbmodem1101 [READY]
```

### Step 2: Test Optical Alignment & Lens Focus
Mount the 850nm bandpass filter in front of the camera lens, connect the camera, and launch the terminal visualizer:
```bash
python3 scripts/bench_tool.py --mode=camera-align --device=0
```
*Action:* Point the camera at the blinking 850nm LED across your desk. Rotate the lens focus ring until the live ASCII terminal display focuses from a fuzzy cloud into a sharp centroid marker `[*]`:
```
+----------------------------------------+
|                                        |
|                   ***                  |
|                   ***                  |
|                                        |
+----------------------------------------+
  -> BLOB #1: Intensity=245/255 | Area=12px | Azimuth=-12 mrad | Elevation=+4 mrad
```

### Step 3: Live Pulse Stream & CRC-8 Decoding
Point the camera directly at the breadboard emitter:
```bash
python3 scripts/bench_tool.py --mode=rx-decode --device=0
```
*Expected Output:*
```
[14:22:05] RECOVERED FRAME #1 | Node=1 | Seq=1 | Mode=2 | Lock=3 | ACK=True | Bearing=-12 mrad | CRC=0x31 [VALID]
[14:22:05] RECOVERED FRAME #2 | Node=1 | Seq=2 | Mode=2 | Lock=3 | ACK=True | Bearing=-11 mrad | CRC=0x8C [VALID]
```

### Step 4: Full Multi-Node Swarm Run
Launch the production Panda Runtime:
```bash
python3 -m runtime.panda.engine
```
The node will acquire optical lock, participate in The Cupboard decentralized consensus, and relay validated discrete state packets across UDP to the Zenoh tactical gateway.
