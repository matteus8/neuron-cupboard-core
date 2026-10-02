# Subsystem: gcs/ (Ground Control Station & Tactical C2 Dashboard)

`gcs/` is the Ground Control Station tactical telemetry receiver and real-time Head-Up Display (HUD) web dashboard for Neuron Cupboard. It runs as a single, zero-dependency static binary on ground station laptops (e.g., Microsoft Surface Pro running Ubuntu), command posts, or field workstations.

## Operational Capabilities
* **Optical Wire Ingestion:** Ingests 6-byte raw optical wire frames over UDP or connects to tactical relay feeds.
* **Embedded Tactical HUD:** Serves a high-contrast dark-mode tactical web dashboard on `:8080` (zero external CDN or npm dependencies; fully air-gapped capable).
* **Optical Bearing Radar:** Renders a polar radar plotting active node azimuth ($\pm 350\text{ mrad}$) and elevation bearing angles in real time.
* **The Cupboard Swarm Telemetry:** Live fleet consensus cards showing operational mode, optical lock status, sequence counter, and consensus flags.
* **Live Wire Console:** Rolling stream of ingested frames with CRC-8 validation checks.
* **Simulation / Demo Mode:** Built-in `--demo` engine generating multi-node optical swarm telemetry for offline hardware verification.

## Build and Run

```bash
# Run unit tests with race detection
cd gcs && go test -v -race ./...

# Build binary
cd gcs && go build -o ../bin/gcs .

# Run in simulation demo mode (access dashboard at http://localhost:8080)
./bin/gcs --demo

# Run live on ground station laptop (e.g. Surface Pro 3 on Ubuntu)
./bin/gcs --http-addr 0.0.0.0:8080 --listen-addr 0.0.0.0:9092
```

## CLI Flags

| Flag | Default | Description |
| :--- | :--- | :--- |
| `--http-addr` | `0.0.0.0:8080` | Web dashboard HTTP server address. |
| `--listen-addr` | `0.0.0.0:9092` | UDP port listening for decoded optical wire frames. |
| `--gateway-cmd` | `127.0.0.1:9090` | UDP address of tactical gateway for command dispatch. |
| `--demo` | `false` | Enable multi-node optical swarm simulation generator. |
