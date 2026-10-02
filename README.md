# Neuron Cupboard Core

Physical-layer optical transceiver payloads (**Bamboo Nodes**) and deterministic edge compute for autonomous swarm coordination under absolute RF silence and zero GPS reliance. Nodes communicate strictly via modulated 850nm Infrared light (Manchester-encoded pulse trains) captured by bandpass-filtered monochrome cameras.

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
