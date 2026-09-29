# Bamboo Node: Hardware Procurement & Bench Bringup Guide

The complete software stack (wire codecs, PIO transmitter firmware, dual-aperture vision, SDMA spatial multi-tracking, consensus engine, and tactical Zenoh gateway) is fully implemented, verified with 27 unit/fuzz tests, and audited by SAST.

When you are ready to transition from software simulation to physical hardware testing, this guide provides the exact components to order and the desktop bench verification sequence.

---

## 1. Bill of Materials (BOM) & Sourcing Checklist

### Tier 1: Microcontroller & 850nm Transmitter (~$18 – $22 total)
| Component | Recommended Part / Model | Purpose | Approx. Cost |
| :--- | :--- | :--- | :--- |
| **Microcontroller** | Raspberry Pi Pico (RP2040) with pre-soldered headers | Executes zero-jitter Manchester PIO modulation | $5.00 |
| **IR Emitter** | Vishay TSAL6100 (850nm high-power IR LED, 5mm package) | Emits modulated optical beacon ($\lambda_p = 850\,\text{nm}$) | $4.50 (pack of 5) |
| **Switching FET** | 2N7000 (TO-92 through-hole) or IRLML2502 | Logic-level N-channel MOSFET switching the LED rail | $2.50 (pack of 5) |
| **Resistors** | <ul><li>$1\times 22\,\Omega$ (1W or 2W power rating, current limiting)</li><li>$1\times 100\,\Omega$ (1/8W, gate damping)</li><li>$1\times 10\text{ k}\Omega$ (1/8W, gate pulldown)</li></ul> | Sets ~150mA pulse current and protects Pico GPIO | $3.00 (assorted kit) |
| **Prototyping** | 400-point solderless breadboard + male-to-male jumper wires | Circuit assembly without soldering | $5.00 |

### Tier 2: Optical Sensor & Compute (~$35 – $110 total)
| Component | Recommended Part / Model | Purpose | Approx. Cost |
| :--- | :--- | :--- | :--- |
| **Edge Compute** | Raspberry Pi 5 (4GB or 8GB) *(or developer laptop for bench testing)* | Runs the Panda edge runtime and Zenoh bridge | $60.00 *(or $0 if already owned)* |
| **Monochrome Sensor** | Raspberry Pi Global Shutter Camera (Sony IMX296) or Arducam OV9281 | Eliminates rolling shutter skew during pulse decoding | $25.00 – $50.00 |
| **Camera Lens** | M12 Mount Lens (6mm or 8mm focal length) | Focuses the optical image onto the sensor | $8.00 |
| **Pi 5 CSI Cable** | 22-pin 0.5mm to 15-pin 1.0mm flex ribbon cable (150mm) | Connects camera to Raspberry Pi 5 CAM0 port | $3.50 |

### Tier 3: Optical Isolation Filter (~$15 – $25 total)
| Component | Recommended Part / Model | Purpose | Approx. Cost |
| :--- | :--- | :--- | :--- |
| **Bandpass Filter** | 850nm Narrowband Optical Bandpass Filter (FWHM 10–20nm, 12mm or 25mm diameter) | Blocks ambient sunlight (400–750nm); renders dark background | $18.00 |

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
