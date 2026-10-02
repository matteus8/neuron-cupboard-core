# Neuron Cupboard Core

Physical-layer optical transceiver payloads (**Bamboo Nodes**) and deterministic edge compute for autonomous swarm coordination under absolute RF silence and zero GPS reliance. Nodes communicate strictly via modulated 850nm Infrared light (Manchester-encoded pulse trains) captured by bandpass-filtered monochrome cameras.

## Release Artifacts & Target Hardware Guide

Every release publishes standalone, statically linked binaries and microcontroller firmware with zero external dependencies:

| Artifact File | Target Hardware | Execution Role & Installation |
| :--- | :--- | :--- |
| **`bamboo_node.uf2`** | **Raspberry Pi Pico H** (RP2040 MCU) | **Optical Transmitter:** Hold `BOOTSEL` button while connecting Pico via USB (`RPI-RP2` drive). Drag & drop this file. Pico auto-reboots and begins 1000-baud Manchester IR transmission on GP15. |
| **`gateway-linux-arm64`** | **Raspberry Pi 5** (64-bit ARM) | **Tactical Relay Daemon:** Bridges physical optical mesh packets to Eclipse Zenoh networks. Execute standalone or enable via `deploy/systemd/neuron-gateway.service`. |
| **`gateway-linux-amd64`** | **x86_64 Workstations / Servers** | **Tactical Command Post Bridge:** Ingests swarm state vectors on tactical edge servers and Linux ground stations. |
| **`gateway-darwin-arm64`** | **Apple Silicon Mac** (macOS) | **Local Telemetry & Dev Bridge:** Local simulation and real-time monitoring on macOS workstations. |
| **`checksums.sha256`** | All Platforms | **Verification Manifest:** Cryptographic SHA-256 hashes for all release artifacts (`sha256sum -c checksums.sha256`). |

> [!NOTE]
> **Panda Edge Compute Runtime (`runtime/`):** Runs on the **Raspberry Pi 5** host OS (requires Python 3 + OpenCV). It ingests video from the Camera Module 3 NoIR, detects optical centroids, decodes pulses, and updates swarm consensus. Launch via `python3 -m runtime.panda.engine` or install the systemd unit `deploy/systemd/panda-runtime.service`.

## Subsystems

* **`proto/`**: Single source of truth for message schemas (`neuron.proto`) and 6-byte wire codecs (C/Go/Python).
* **`firmware/`**: RP2040 bare-metal C / PIO hardware Manchester 850nm IR transmitter.
* **`runtime/`**: Raspberry Pi 5 Panda Runtime (zero-bloat optical vision, pulse decoder, swarm consensus).
* **`gateway/`**: Tactical network bridge publishing optical mesh states over Eclipse Zenoh.

## Core Terminology
* Bamboo Node: The physical transceiver payload (RP2040 microcontroller + 850nm IR LED emitter + monochrome camera + Raspberry Pi 5).
* Neuron: The fundamental state packet transmitted over the modulated optical beam.
* The Cupboard: The decentralized swarm consensus state shared among active nodes in optical line-of-sight.
* Panda Runtime: The deterministic edge execution engine running on the Raspberry Pi 5.

## Quick Start

```bash
make test      # Verify subsystems & E2E simulation
make sast      # Multi-language SAST audits (gosec, bandit, clang)
make bench     # Zero-allocation throughput benchmarks
```
Releases are built via CI on semver tags (`v*.*.*`), producing stripped standalone binaries.
