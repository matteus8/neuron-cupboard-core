# Subsystem: gateway/ (Tactical Network Bridge)

`gateway/` bridges the optical line-of-sight mesh to external tactical networks via Eclipse Zenoh. Relay nodes ingest raw physical Manchester-decoded frames, translate them into compact `neuron.v1.Neuron` Protobuf payloads, and publish them to constrained tactical networks.

## Operational Constraints
* **Low Overhead:** Zero-copy byte buffer handling where possible, minimal heap allocations, and zero GC pause spikes on publish paths.
* **Deterministic Timeouts:** All network and queue publish calls have bounded non-blocking contexts (default 50ms).
* **Headless:** Outputs structured key-value stdout logs.

## Zenoh Key Expressions
* `neuron/mesh/<node_id>/state`: Serialized Protobuf `Neuron` packet broadcast by individual Bamboo Nodes.
* `neuron/cupboard/consensus`: Swarm-level consensus state (`TheCupboard`) computed across active nodes.

## Build and Run
```bash
# Run unit tests
go test -v ./...

# Build binary
go build -o bin/gateway .

# Run with Zenoh endpoint
./bin/gateway -zenoh-router tcp/127.0.0.1:7447 -listen-addr 127.0.0.1:9090
```
