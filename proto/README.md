# Subsystem: proto/ (Neuron Cupboard Protocol Specifications)

`proto/` serves as the single source of truth for message schemas, physical frame dynamics, and bit-level state mappings for the optical transceiver mesh.

## Wire Framing (Physical Optical Link)
Physical communication over the 850nm IR Manchester optical link operates on fixed 6-byte (48-bit) deterministic frames:

| Byte Offset | Field Name | Description | Value / Constraint |
|:---|:---|:---|:---|
| 0 | `preamble` | Manchester sync pulse sequence | `0xAA` (10101010b) |
| 1 | `sync_word` | Frame start delimiter | `0xD5` (11010101b) |
| 2 | `node_id` | Transmitting Bamboo Node ID | `1 - 255` |
| 3 | `seq_num` | Monotonic frame sequence counter | `0 - 255` |
| 4 | `state_byte` | Compact 8-bit discrete state vector | See bitfield below |
| 5 | `crc8` | CRC-8-CCITT Checksum | Poly `0x07`, Init `0x00` over Bytes [2:5] |

## 8-Bit Discrete State Vector Mapping
```
 Bit:  7       6       5       4       3   2       1   0
     +-------+-------+-------+-------+-------+---+-------+---+
     | SYNC  | SWAP  | PROX  | CONS  | LOCK STATUS | OPER MODE |
     +-------+-------+-------+-------+-------+---+-------+---+
```
* **Bits [0:1] - OperationalMode:**
  * `00` (`0x00`) - `MODE_UNSPECIFIED`
  * `01` (`0x01`) - `MODE_SEARCH` (Dispersed optical search pattern)
  * `10` (`0x02`) - `MODE_FORMATION_LOCK` (Bearing-locked synchronized formation)
  * `11` (`0x03`) - `MODE_DISPERSAL` (Tactical scatter / collision avoidance)
* **Bits [2:3] - OpticalLockStatus:**
  * `00` (`0x00`) - `LOCK_NONE` (No optical emitter detected)
  * `01` (`0x01`) - `LOCK_ACQUIRING` (Intermittent 850nm pulse train detected)
  * `10` (`0x02`) - `LOCK_TRACKING` (Centroid bearing lock active)
  * `11` (`0x03`) - `LOCK_HARD_LOCKED` (Two-way optical handshake confirmed)
* **Bit 4 (`0x10`) - Consensus ACK:** Swarm consensus quorum acknowledgment.
* **Bit 5 (`0x20`) - Proximity Alert:** Optical anti-collision / near-field proximity warning.
* **Bit 6 (`0x40`) - SWaP Critical:** Size, Weight, and Power alert (critical power threshold).
* **Bit 7 (`0x80`) - Frame Sync Marker:** Physical pulse alignment beacon.

## Codec Implementations
* **Bare-metal C:** `proto/neuron_wire.h` / `proto/c/neuron_wire.h` (Zero heap allocation, static inline CRC-8 and bitfield pack/unpack routines).
* **Pure Python / MicroPython:** `proto/neuron_wire.py` (Zero external dependencies).
* **Go:** `proto/wire.go` (Maps 6-byte physical frames directly to `*neuronv1.Neuron` Protobuf messages).
* **Protobuf Schema:** `proto/neuron.proto` (Generated for Go in `gen/go/` and Python in `gen/py/`).
