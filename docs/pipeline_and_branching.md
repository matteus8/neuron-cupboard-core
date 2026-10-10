# Pipeline, SAST, and Branching Architecture

## 1. Branching Strategy

The repository follows a hardened trunk-based branching workflow optimized for high-reliability embedded platforms:

```
[ feat/optical-gating ] ──┐
                          ├──> [ Pull Request + CI Quality Gate ] ──> [ main ] ──> Tag: v1.0.0 ──> [ Release ]
[ fix/crc8-edge-case   ] ──┘
```

* **`main` (Protected Production Trunk):**
  - Always clean, verified, and releasable.
  - Requires passing CI checks (`sast` and `build-and-verify`).
* **`feat/*` and `fix/*` (Feature & Fix Branches):**
  - Short-lived topic branches branched off `main`.
  - Continuous Integration triggers on every push and pull request.
* **`release/v*` (Stabilization Branches):**
  - Dedicated stabilization branches for tactical field deployments when backporting fixes.
* **CI Concurrency Optimization:**
  - Automated `concurrency: cancel-in-progress: true` prevents wasted compute cycles by canceling superseded runs on in-flight pull requests.

---

## 2. Static Application Security Testing (SAST)

Security audits are enforced locally via `make sast` and remotely in CI prior to any test or build steps:

| Layer | Language / Component | SAST Tool | Enforced Security Controls |
| :--- | :--- | :--- | :--- |
| **Gateway & Wire Codec** | Go | `gosec` | Integer overflow detection (CWE-190), HTTP header Slowloris protection (CWE-400), context lifecycle validation |
| **Vulnerability Audit** | Go | `govulncheck` | Real-time checks against the official Go Vulnerability Database |
| **Panda Runtime & Vision** | Python | `bandit` | AST inspection for unsafe exception handling, socket leaks, and insecure randomness |
| **Bare-Metal Firmware & Wire** | C (C99) | `cppcheck` & `clang` | Hardened flags (`-Wformat-security`, `-Wconversion`), bounds verification, uninitialized variable checks |

To run the full multi-language security audit locally:
```bash
make sast
```

---

## 3. Zero-Container Release Architecture

In adherence to the Neuron Cupboard SWaP (Size, Weight, and Power) engineering constraints:
* **No Docker Daemons or Containers:** Drones and microcontrollers run bare-metal or native headless processes. Containers add storage overhead, memory fragmentation, and non-deterministic process scheduling latency.
* **Native Standalone Binaries & Firmware:** The release pipeline cross-compiles statically linked, stripped binaries and bare-metal microcontroller firmware with zero runtime dependencies:
  - `bamboo_node.uf2`: Bare-metal optical transmitter firmware for the Raspberry Pi Pico H (RP2040 MCU) with cycle-accurate PIO Manchester modulation.
  - `gateway-linux-arm64`: Targeted for Raspberry Pi 5 / ARM Cortex-A76 edge nodes.
  - `gateway-linux-amd64`: Targeted for tactical x86_64 edge workstations and Zenoh routers.
  - `panda-runtime.tar.gz`: Lightweight edge runtime bundle for Raspberry Pi 5.
  - `panda-runtime-airgap.tar.gz`: DDIL / air-gapped installation package with bundled asset directories (`wheels/` and `debs/`) and `--airgap` flag support to operate without internet access.
  - `checksums.sha256`: Cryptographic SHA-256 verification manifest.

### 4. DDIL & Air-Gapped Field Deployment
In disconnected, denied, intermittent, or limited-bandwidth (DDIL) environments where nodes cannot reach external package repositories:
* The installer provides `--airgap` / `--offline` flags:
  ```bash
  sudo ./install.sh --airgap
  ```
* Dependencies are pre-verified against local Python and system caches before touching the network.
* Offline wheels in `./wheels/` and Debian packages in `./debs/` are auto-detected and installed locally (`pip --no-index --find-links` and `dpkg -i`).

### Triggering a Release
To publish an official release, push a signed semantic version tag:
```bash
git tag -a v1.0.0 -m "Release v1.0.0: Initial operational mesh transceiver release"
git push origin v1.0.0
```
GitHub Actions will run SAST, execute all test suites, cross-compile release binaries, and publish the release with assets automatically attached.
