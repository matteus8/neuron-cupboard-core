# Neuron Cupboard Core

Physical-layer optical transceiver payloads (**Bamboo Nodes**) and deterministic edge compute for autonomous swarm coordination under absolute RF silence and zero GPS reliance. Nodes communicate strictly via modulated 850nm Infrared light (Manchester-encoded pulse trains) captured by bandpass-filtered monochrome cameras.

## Subsystems

* **`proto/`**: Single source of truth for message schemas (`neuron.proto`) and 6-byte wire codecs (C/Go/Python).
* **`firmware/`**: RP2040 bare-metal C / PIO hardware Manchester 850nm IR transmitter.
* **`runtime/`**: Raspberry Pi 5 Panda Runtime (zero-bloat optical vision, pulse decoder, swarm consensus).
* **`gateway/`**: Tactical network bridge publishing optical mesh states over Eclipse Zenoh.

## Quick Start

```bash
# Build and run all subsystem unit tests
make test

# Run multi-node optical swarm simulation
make test-sim
```
