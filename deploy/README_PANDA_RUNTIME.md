# Neuron Cupboard: Panda Edge Runtime (Raspberry Pi 5)

Deterministic edge computer vision and decentralized swarm consensus engine for **Bamboo Nodes**.

---

## 1. Quick Start Installation

1. **Extract Archive:**
   ```bash
   tar -xzf panda-runtime.tar.gz
   ```

2. **Run Zero-Touch Installer:**
   Replace `<LAPTOP_IP>` with the IP address of your Ground Control Station (GCS) operator laptop:
   ```bash
   sudo ./install.sh --gateway-ip <LAPTOP_IP> --gateway-port 9092
   ```

3. **Verify Active Service:**
   ```bash
   sudo systemctl status panda-runtime.service
   journalctl -u panda-runtime.service -f
   ```

---

## 2. Directory Structure

When extracted, this package contains:

```text
├── install.sh                  # Production edge installer for Raspberry Pi OS Lite (64-bit)
├── install_gateway.sh          # Optional collocated Zenoh gateway installer
├── panda-runtime.service       # Hardened systemd service descriptor (RT scheduling RR, prio 45)
├── neuron-gateway.service      # Systemd service descriptor for Zenoh network relay
├── requirements.txt            # Python dependencies (OpenCV, NumPy)
├── runtime/                    # Core Panda edge vision and swarm consensus engine
│   └── panda/
│       ├── camera.py           # V4L2/libcamera front-end & synthetic simulator
│       ├── vision.py           # Optical tracker (OpenCV morphology & contour moments)
│       ├── decoder.py          # Manchester stream decoder (IEEE 802.3, 15 Baud)
│       ├── multi_tracker.py    # Spatial multi-target tracker (SDMA gating)
│       ├── cupboard.py         # Swarm consensus state machine & stale node eviction
│       └── engine.py           # Headless edge daemon with non-blocking timeouts
├── proto/                      # Protocol Buffers & 6-byte wire codecs (Python/C)
└── scripts/
    ├── bench_tool.py           # Interactive optical alignment HUD & pulse decoder tool
    └── run_runtime.sh          # Daemon runner script bridging libcamera/PiSP via libcamerify
```

---

## 3. Interactive Bench & Diagnostics Tools

Before or alongside running the background service, you can run interactive diagnostics directly from the command line:

> [!NOTE]
> If `panda-runtime.service` is running, stop it first so it releases `/dev/video0`:
> ```bash
> sudo systemctl stop panda-runtime.service
> ```

### A. Live Optical Front-End Alignment & Focus HUD
Aim your 850nm transmitter at the lens and run:
```bash
libcamerify python3 scripts/bench_tool.py --mode=camera-align --iterations=0
```
- Displays a real-time ASCII terminal grid representing the camera's field of view.
- Displays spot intensity (`0-255`), contour area (`px`), and azimuth/elevation bearings (`mrad`).
- Adjust lens focus until a saturated `[*]` cluster appears at boresight.

### B. Live Pulse Decoder & Manchester Stream Inspector
Listen for physical 850nm Manchester-modulated packets:
```bash
libcamerify python3 scripts/bench_tool.py --mode=rx-decode --duration=30 --threshold=175 --min-area=8 --max-area=2000
```
- Reports live pulse presence (`●` / `○`), active tracks, accumulated bitstream in hex, and CRC-8 validation.
- Decodes full 6-byte frames (`Node ID`, `Sequence Number`, `State`, `Bearing`, `CRC-8`).

---

## 4. Configuration File Reference (`/etc/default/panda-runtime`)

The installer provisions `/etc/default/panda-runtime`, which is automatically ingested by `panda-runtime.service`:

```ini
# Neuron Cupboard Panda Runtime Configuration
NEURON_CAMERA_DEVICE=0
NEURON_TARGET_FPS=30.0
NEURON_LUMINANCE_THRESHOLD=175
NEURON_MIN_BLOB_AREA=8.0
NEURON_MAX_BLOB_AREA=2000.0
NEURON_GATEWAY_IP=10.165.22.228
NEURON_GATEWAY_PORT=9092
```

### Parameter Explanations:
* `NEURON_CAMERA_DEVICE`: V4L2 device index (`0` for `/dev/video0`).
* `NEURON_TARGET_FPS`: Camera integration frequency (`30.0` FPS, matching 15 Baud half-bit chips).
* `NEURON_LUMINANCE_THRESHOLD`: Luminance cut-off (`175`, rejecting ambient room light and table glare while capturing 850nm LED peaks).
* `NEURON_MIN_BLOB_AREA`: Minimum contour area in pixels (`8.0`, rejecting 1-2px CMOS shot noise).
* `NEURON_MAX_BLOB_AREA`: Maximum contour area in pixels (`2000.0`, rejecting large diffuse reflection blooms).
* `NEURON_GATEWAY_IP`: Target IP address of the Ground Control Station (GCS) or Zenoh Gateway.
* `NEURON_GATEWAY_PORT`: Target UDP port (`9092`).

After modifying configuration:
```bash
sudo systemctl restart panda-runtime.service
```

---

## 5. Hardware Requirements

* **SBC:** Raspberry Pi 5 (Raspberry Pi OS Lite 64-bit, Debian Bookworm).
* **Sensor:** Raspberry Pi Camera Module 3 NoIR (Sony IMX708, connected via MIPI CSI).
* **Optical Filter:** 12.5mm x 1.0mm 850nm Narrow Bandpass Filter Disc mounted flush on lens.
* **Transmitter Node:** Raspberry Pi Pico H (RP2040) running `bamboo_node.uf2` firmware (GPIO 15 driving 2N7000 MOSFET + 850nm IR LED at 15 Baud).
