# Neuron Cupboard: Physical-Layer Optical Swarm Consensus

[![CI Pipeline](https://github.com/matteus8/neuron-cupboard-core/actions/workflows/ci.yml/badge.svg)](https://github.com/matteus8/neuron-cupboard-core/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-emerald.svg)](LICENSE)
[![Platform: ARM64 & RP2040](https://img.shields.io/badge/Hardware-RP2040%20%7C%20Pi%205%20%7C%20IMX708-blue.svg)]()
[![Security: Hardened](https://img.shields.io/badge/Security-SAST%20Clean%20%7C%20Memory%20Safe-success.svg)]()

> **Physical-layer optical transceiver payloads ("Bamboo Nodes") and deterministic edge compute for autonomous swarm coordination under absolute RF silence and zero GPS reliance.**

Swarm nodes communicate strictly via modulated **850nm Infrared light** (Manchester-encoded pulse trains) captured by narrowband bandpass-filtered monochrome cameras. The system achieves decentralized quorum consensus and relative spatial bearing localization without emitting a single radio photon.

---

## 1. System Architecture & Subsystems

```text
+----------------------------------------------------------------------------------------------------+
|                                    PHYSICAL TESTBED TOPOLOGY                                       |
|                                                                                                    |
|  [ TRANSMITTER: BREADBOARD PAYLOAD ]                                                               |
|  Raspberry Pi Pico H (RP2040 Dual Cortex-M0+ @ 125MHz)                                             |
|    └─ GPIO 15 -> 100 Ohm Gate Resistor -> 2N7000 N-Channel MOSFET                                  |
|    └─ 5V VBUS -> 25 Ohm (4x 100 Ohm, 1W) Resistor Bank -> 850nm High-Power IR LED (Chanzon 5mm)     |
|                                                                                                    |
|           ~~~ 850nm Manchester Modulated Photons (Line-of-Sight, 15 Baud, 0.5m - 2.0m) ~~~        |
|                                                                                                    |
|  [ RECEIVER / EDGE COMPUTE: BAMBOO NODE ]                                                          |
|  Raspberry Pi 5 (Quad Cortex-A76 @ 2.4GHz, BCM2712 RP1 Southbridge, Debian Bookworm 64-bit)        |
|    ├─ Camera: Raspberry Pi Camera Module 3 NoIR (Sony IMX708 via MIPI CSI-2)                       |
|    ├─ Optical Filter: 12.5mm x 1.0mm 850nm Narrowband Bandpass Optical Glass Disc flush on lens    |
|    ├─ ISP Bridge: libcamera / PiSP -> libcamerify -> OpenCV / V4L2 @ 640x480 RGB888, 30 FPS       |
|    └─ Engine: panda-runtime.service (systemd RT daemon with spatial SDMA & TheCupboard state)      |
|                                                                                                    |
|           ~~~ Wi-Fi / Tactical Hotspot UDP Datagrams (Port 9092) ~~~                               |
|                                                                                                    |
|  [ OPERATOR STATION: COMMAND & CONTROL (C2) ]                                                      |
|  Tactical Laptop (Windows 11 / macOS / Linux Workstation)                                          |
|    ├─ Ingest Daemon: scripts/gcs_server.py (or bin/gcs-linux-amd64 / Docker container)             |
|    └─ Tactical Web HUD: http://localhost:8080 (Dark-Mode Polar Radar & Swarm Consensus Visualizer)  |
+----------------------------------------------------------------------------------------------------+
```

### Subsystems Monorepo Structure:
* **[`proto/`](file:///home/ubuntu-root/github/neuron-cupboard-core/proto/)**: Single source of truth for message schemas ([`neuron.proto`](file:///home/ubuntu-root/github/neuron-cupboard-core/proto/neuron.proto)) and 6-byte packed physical wire codecs across C, Go, and Python.
* **[`firmware/`](file:///home/ubuntu-root/github/neuron-cupboard-core/firmware/)**: Bare-metal C and PIO assembly for the RP2040 microcontroller (Raspberry Pi Pico H). Implements microsecond hardware timers and IEEE 802.3 Manchester pulse modulation over GPIO 15.
* **[`runtime/`](file:///home/ubuntu-root/github/neuron-cupboard-core/runtime/)**: **Panda Runtime** for Raspberry Pi 5. Ingests raw camera frames, executes hardware-accelerated OpenCV morphological filtering, extracts spatial centroids, decodes concurrent Manchester bitstreams (SDMA), and manages the decentralized swarm consensus engine.
* **[`gateway/`](file:///home/ubuntu-root/github/neuron-cupboard-core/gateway/)**: Tactical network relay translating optical mesh states into compact Protocol Buffer payloads published over **Eclipse Zenoh**.
* **[`gcs/`](file:///home/ubuntu-root/github/neuron-cupboard-core/gcs/) & [`scripts/gcs_server.py`](file:///home/ubuntu-root/github/neuron-cupboard-core/scripts/gcs_server.py)**: Tactical Ground Control Station (GCS) providing a real-time dark-mode polar radar HUD and wire stream inspector on `http://localhost:8080`.

---

## 2. The Engineering Case Study: Deep Struggles & Breakthroughs

> *A technical write-up for engineering leaders, hiring managers, and embedded systems architects on the real-world physical and software hurdles solved during this project.*

### Challenge 1: Camera Exposure Integration vs. Transmitter Baud Rate
* **The Symptom:** Initial physical tests produced pristine optical alignment on the lens, but the Manchester receiver decoded **0 frames** over 30 seconds.
* **The Root Cause:** The original RP2040 firmware transmitted pulses at **1000 Baud** ($500\,\mu\text{s}$ chips), completing all 96 chips in $48\text{ ms}$. However, the Sony IMX708 camera integrates photons over a $33.3\text{ ms}$ rolling shutter window ($30\text{ FPS}$). The camera integrated $\sim 66$ pulses into a single exposure, seeing a constant solid light rather than distinct high/low transitions. The software decoder received continuous `1, 1, 1, 1` chips, rejecting them as illegal Manchester transition violations.
* **The Solution:** We re-engineered the physical layer around the Nyquist integration rate of the optical front-end:
  $$\text{Baud Rate} = \frac{30\text{ FPS}}{2\text{ chips/bit}} = 15\text{ Baud} \quad (\tau_{\text{chip}} = 33.333\,\text{ms})$$
  By adapting [`firmware/src/main.c`](file:///home/ubuntu-root/github/neuron-cupboard-core/firmware/src/main.c) to 15 Baud with microsecond timer precision, we achieved exact hardware synchronization with the camera’s **29.9 FPS** integration clock (measured interval delta $< 110\,\mu\text{s}$).

### Challenge 2: Ambient Glare, Table Reflection Bloom, and Manchester Bit Flips
* **The Symptom:** At lower luminance thresholds ($\le 150$), the live Manchester inspector captured bytes such as `0xAF` and `0xD7`, but could never lock onto frames.
* **The Root Cause:** In our bench setup, the physical desk surface in front of the lens ($y=460\text{–}478$ on a $640\times 480$ sensor) produced a diffuse $20,554\text{ px}$ reflection bloom with an intensity of $I=176$. Because the reflection sat above the threshold, it **never turned dark** during the LED's low half-bits (0-chips). The table bloom acted as an ambient light source, turning intended `0` chips into `1` chips:
  - Expected Preamble (`0xAA` = `10101010b`) flipped to `0xAF` (`10101111b`).
  - Expected Sync Word (`0xD5` = `11010101b`) flipped to `0xD7` (`11010111b`).
  - Furthermore, the 20,500px reflection fragmented into 18 competing tracks, exhausting the spatial tracker.
* **The Solution:** We designed a multi-stage rejection pipeline:
  1. **Morphological Opening:** Applied a $3\times 3$ structuring element (`cv2.morphologyEx(..., cv2.MORPH_OPEN)`) to immediately eliminate high-frequency CMOS shot noise.
  2. **Calibrated Acceptance Window:** Set `luminance_threshold=175`, `min_blob_area=8.0px`, and `max_blob_area=2000.0px`. This cleanly eliminated both the 2px sensor noise and the 20,500px table glare, isolating the true 850nm LED centroid ($I \approx 200\text{–}255$, $A \approx 338\text{ px}$).
* **The Result:** The spurious tracks instantly collapsed from 18 to **1**, and the receiver immediately achieved **100% frame recovery** over the air.

### Challenge 3: Modern Linux Kernel Camera Pipelines on Raspberry Pi 5
* **The Challenge:** Raspberry Pi OS Debian Bookworm on the BCM2712 architecture abandoned the legacy V4L2 kernel driver stack in favor of **libcamera** and the hardware **PiSP** (Raspberry Pi Image Signal Processor). Standard OpenCV `VideoCapture(0)` calls failed with `Device or resource busy` or segmentation faults.
* **The Solution:** We engineered a transparent daemon wrapper in [`scripts/run_runtime.sh`](file:///home/ubuntu-root/github/neuron-cupboard-core/scripts/run_runtime.sh) utilizing `libcamerify` from `libcamera-tools`. This hooks userspace V4L2 system calls into the libcamera pipeline, providing raw zero-copy access to ISP frames while preserving full hardware compatibility with standard OpenCV C++ routines.

### Challenge 4: Cross-Network Virtualization NAT (Windows / WSL2 / Wi-Fi)
* **The Challenge:** When running the GCS ingest server inside a WSL2 Linux environment, incoming UDP packets broadcast by the Pi 5 to the laptop’s physical Wi-Fi IP (`10.165.22.228:9092`) were silently dropped by the Windows Hyper-V NAT boundary.
* **The Solution:** Rather than forcing operators to maintain brittle Windows portproxy rules or virtual network bridges, we built [`scripts/gcs_server.py`](file:///home/ubuntu-root/github/neuron-cupboard-core/scripts/gcs_server.py)—a standalone, zero-dependency Python GCS server that embeds the entire dark-mode HUD web frontend. Running directly on host Windows PowerShell, it binds natively to the physical Wi-Fi socket with zero NAT friction.

---

## 3. Physical Verification & The "Book Test"

During live hardware bench testing, the system demonstrated deterministic optical packet decoding and obstacle recovery:

```text
[15:47:23] level=INFO node=1 seq=198 mode=FORMATION_LOCK lock=HARD_LOCKED ack=1 az_mrad=+50 event=node_joined
[15:47:26] level=INFO node=1 seq=199 mode=FORMATION_LOCK lock=HARD_LOCKED ack=1 az_mrad=+50 event=node_joined
[15:47:30] level=INFO node=1 seq=200 mode=FORMATION_LOCK lock=HARD_LOCKED ack=1 az_mrad=+50 event=node_joined
[15:47:34] level=INFO node=1 seq=201 mode=FORMATION_LOCK lock=HARD_LOCKED ack=1 az_mrad=+50 event=node_joined
[15:47:37] level=INFO node=1 seq=202 mode=FORMATION_LOCK lock=HARD_LOCKED ack=1 az_mrad=+50 event=node_joined
[15:47:41] level=INFO node=1 seq=203 mode=FORMATION_LOCK lock=HARD_LOCKED ack=1 az_mrad=+50 event=node_joined
[15:47:45] level=INFO node=1 seq=204 mode=FORMATION_LOCK lock=HARD_LOCKED ack=1 az_mrad=+50 event=node_joined
[15:47:48] level=INFO node=1 seq=205 mode=FORMATION_LOCK lock=HARD_LOCKED ack=1 az_mrad=+50 event=node_joined
[15:47:52] level=INFO node=1 seq=206 mode=FORMATION_LOCK lock=HARD_LOCKED ack=1 az_mrad=+50 event=node_joined
[15:47:56] level=INFO node=1 seq=207 mode=FORMATION_LOCK lock=HARD_LOCKED ack=1 az_mrad=+50 event=node_joined
[15:48:03] level=INFO node=1 seq=209 mode=FORMATION_LOCK lock=HARD_LOCKED ack=1 az_mrad=+50 event=node_joined
[15:48:07] level=INFO node=1 seq=210 mode=FORMATION_LOCK lock=HARD_LOCKED ack=1 az_mrad=+50 event=node_joined
```

### The Physical Obstruction ("Book Test"):
1. **Obstruction Event:** Placing an opaque physical obstacle (a book or hand) directly between the 850nm LED and the camera lens broke line-of-sight.
2. **Immediate State Transition:** The Panda Runtime immediately detected the loss of optical carrier and logged:
   ```text
   level=WARN ts=... node=1 event=optical_los_lost
   ```
   On the GCS dashboard, the node card transitioned to line-of-sight warning, proving real-time collision and link-drop detection.
3. **Automatic Recovery:** Upon removing the obstacle, the receiver locked onto the optical carrier within **$< 3.5\text{ seconds}$**, rejoining the consensus quorum and resuming sequence tracking without requiring system restarts.

---

## 4. Architectural Tradeoffs: Free-Space Optical (FSO) vs. Radio Frequency (RF)

| Dimension | Radio Frequency (RF / Wi-Fi / UWB) | Free-Space Optical (850nm IR) |
| :--- | :--- | :--- |
| **Obstacle Tolerance** | **Superior:** Readily penetrates non-metallic obstacles, foliage, and structures (NLOS). | **Fragile:** Zero penetration through opaque physical barriers. Strict line-of-sight required. |
| **Electronic Warfare (EW)** | **Vulnerable:** Easily detected, intercepted, jammed, or spoofed by commercial/tactical RF jammers. | **Immune:** Cannot be jammed by radio frequency electronic warfare suites. Total RF silence. |
| **Signature & Interception** | **High:** Omnidirectional isotropic radiation acts as an RF beacon, exposing drone positions to SIGINT. | **Covert (LPD/LPI):** Produces zero radio emissions. Signal is confined to the optical line-of-sight cone. |
| **Relative Positioning** | **Complex:** Requires multi-antenna AoA (Angle of Arrival) arrays, UWB beacons, or external GPS. | **Native:** The camera sensor directly yields azimuth and elevation bearings ($\text{mrad}$) via optical moments. |
| **Swarm Doctrine Role** | Primary channel for long-range, scattered, non-line-of-sight telemetry. | **Tactical out-of-band fail-safe** for tight formation locking, terminal docking, and contested environments. |

---

## 5. Deployment Guide

### Hardware Roles & Execution

| Hardware Role | Physical Hardware | Deployed Artifacts | Description & Execution |
| :--- | :--- | :--- | :--- |
| **Optical Emitter Node** | **Raspberry Pi Pico H** (RP2040) | [`bin/bamboo_node.uf2`](file:///home/ubuntu-root/github/neuron-cupboard-core/bin/bamboo_node.uf2) | Hold `BOOTSEL` while connecting Pico via USB. Drag & drop `bamboo_node.uf2`. Microcontroller auto-reboots and emits 850nm Manchester pulses on GP15. |
| **Optical Receiver Node** | **Raspberry Pi 5** (Debian Bookworm) | [`bin/panda-runtime.tar.gz`](file:///home/ubuntu-root/github/neuron-cupboard-core/bin/panda-runtime.tar.gz) | Extract `panda-runtime.tar.gz` on Pi and run `sudo ./install.sh --gateway-ip <LAPTOP_IP> --gateway-port 9092`. Automatically provisions and starts `panda-runtime.service`. |
| **Ground Control Station** | **Operator Laptop** (Windows / Mac / Linux) | [`scripts/gcs_server.py`](file:///home/ubuntu-root/github/neuron-cupboard-core/scripts/gcs_server.py) *(or Docker)* | Run `python scripts/gcs_server.py` on laptop. Open `http://localhost:8080` in web browser. |

### Where Does the GCS Belong?
* **On the Operator Laptop / Command Post (Recommended):** The GCS is a Command and Control (C2) situational awareness tool for human operators. It aggregates wire streams, renders the polar radar HUD, and monitors swarm health. Keeping it on the operator laptop preserves edge compute resources on the drone for real-time vision.
* **Containerization vs. Native Binary:**
  * **Tactical Laptops (Windows / macOS):** Run natively via `python scripts/gcs_server.py` or `bin/gcs-windows-amd64.exe`. Native execution avoids virtual machine NAT / Hyper-V UDP drops and starts instantly with zero dependencies.
  * **Enterprise / Cloud / Linux Command Centers:** Deploy via container using [`deploy/docker/Dockerfile.gcs`](file:///home/ubuntu-root/github/neuron-cupboard-core/deploy/docker/Dockerfile.gcs):
    ```bash
    docker build -f deploy/docker/Dockerfile.gcs -t neuron-gcs .
    docker run -d --name gcs -p 8080:8080 -p 9092:9092/udp neuron-gcs
    ```

---

## 6. Next Steps & Milestone: Mule Zenoh & The Tactical Network Gateway

With the physical 850nm optical link, edge computer vision pipeline, and operator GCS fully verified end-to-end, the next milestone focuses on **tactical network mesh integration**:

1. **Collocated Tactical Gateway (`gateway/`):**
   - Translate decoded 6-byte optical wire frames into rich, strongly typed Protocol Buffer payloads (`neuron.proto`).
   - Run `gateway-linux-arm64` on the Raspberry Pi 5 to bridge the optical mesh into external IP networks.
2. **Eclipse Zenoh Zero-Overhead Pub/Sub:**
   - Publish decentralized swarm state vectors across constrained, lossy, and ad-hoc wireless networks using Eclipse Zenoh.
   - Demonstrate multi-broker routing and peer-to-peer mesh synchronization across multiple physical Bamboo Nodes.

---

## 7. Build, Test, and Verify

```bash
# Run unit tests across all runtime, decoder, and state machine suites (34 tests)
PYTHONPATH=. python3 -m unittest discover -s runtime/tests -v

# Run C wire protocol tests & exhaustive CRC-8 robustness verification
make test-proto test-firmware

# Package edge runtime for Raspberry Pi 5 deployment
make package-runtime
```

---

*Authored by the Neuron Cupboard Core Team. Dedicated to deterministic edge compute, physical-layer resilience, and autonomous swarm robotics under contested operational environments.*
