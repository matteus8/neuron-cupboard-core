# Subsystem: runtime/ (Raspberry Pi 5 Panda Runtime)

`runtime/` houses the Panda Runtime edge execution engine designed for Raspberry Pi 5 single-board computers. It continuously processes camera frames from an 850nm bandpass-filtered optical front-end, tracks optical emitter centroids, decodes Manchester pulse trains, and maintains decentralized swarm consensus in "The Cupboard".

## Operational Profile
* **Host Platform:** Raspberry Pi 5 (Quad ARM Cortex-A76 @ 2.4GHz, 4GB/8GB LPDDR4X).
* **Sensor Input:** Monochrome global-shutter camera equipped with an 850nm optical bandpass filter (ambient light cut, near-black background).
* **Headless:** Headless execution with structured key-value stdout logs (`level=INFO ts=... node=... event=...`).
* **Zero-Bloat Vision:** Strict avoidance of heavy deep learning inference engines (no PyTorch, TensorFlow, or YOLO). Employs fast grayscale luminance thresholding, morphological filtering, and contour moments.

## Architecture
* `panda/vision.py`: Zero-bloat optical centroid detector and milliradian bearing estimator.
* `panda/decoder.py`: Deterministic Manchester stream decoder, preamble sync word finder, and CRC-8 validator.
* `panda/cupboard.py`: Decentralized swarm consensus tracker and TTL node eviction.
* `panda/engine.py`: Bounded-latency edge loop connecting vision, pulse decoding, and consensus state.
* `tests/`: Automated unit tests covering vision geometry, Manchester decoding, and swarm quorum.
