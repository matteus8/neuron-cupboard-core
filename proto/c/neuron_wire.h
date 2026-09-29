/**
 * @file neuron_wire.h
 * @brief Zero-allocation bare-metal C wire protocol definitions for Neuron Cupboard.
 * 
 * Defines physical frame structure, bit-level state mappings for the 8-bit
 * discrete state vector, and bounded-time CRC-8 routines for Manchester-encoded
 * 850nm IR optical links.
 */

#ifndef NEURON_WIRE_H
#define NEURON_WIRE_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Link-layer framing constants */
#define NEURON_WIRE_PREAMBLE       ((uint8_t)0xAA)
#define NEURON_WIRE_SYNC_WORD      ((uint8_t)0xD5)
#define NEURON_WIRE_FRAME_LEN      ((uint8_t)6)     /* Total frame bytes */
#define NEURON_WIRE_PAYLOAD_LEN    ((uint8_t)3)     /* Node ID, Seq, State */

/* Bitmask definitions for the 8-bit discrete state vector */
#define NEURON_STATE_MODE_MASK        ((uint8_t)0x03) /* Bits 0-1 */
#define NEURON_STATE_MODE_SHIFT       (0)

#define NEURON_STATE_LOCK_MASK        ((uint8_t)0x0C) /* Bits 2-3 */
#define NEURON_STATE_LOCK_SHIFT       (2)

#define NEURON_STATE_CONSENSUS_ACK    ((uint8_t)0x10) /* Bit 4: Swarm Consensus ACK */
#define NEURON_STATE_PROXIMITY_ALERT  ((uint8_t)0x20) /* Bit 5: Optical Proximity Warning */
#define NEURON_STATE_SWAP_CRITICAL    ((uint8_t)0x40) /* Bit 6: Size/Weight/Power Critical Alert */
#define NEURON_STATE_SYNC_MARKER      ((uint8_t)0x80) /* Bit 7: Frame Sync Marker */

/* Operational modes (Bits 0-1) */
typedef enum {
    NEURON_MODE_UNSPECIFIED     = 0x00,
    NEURON_MODE_SEARCH          = 0x01,
    NEURON_MODE_FORMATION_LOCK  = 0x02,
    NEURON_MODE_DISPERSAL       = 0x03
} neuron_mode_t;

/* Optical bearing lock status (Bits 2-3) */
typedef enum {
    NEURON_LOCK_NONE            = 0x00,
    NEURON_LOCK_ACQUIRING       = 0x01,
    NEURON_LOCK_TRACKING        = 0x02,
    NEURON_LOCK_HARD_LOCKED     = 0x03
} neuron_lock_status_t;

/**
 * Packed physical wire frame transmitted over modulated 850nm IR.
 * Total size: exactly 6 bytes (48 bits).
 */
#pragma pack(push, 1)
typedef struct {
    uint8_t preamble;    /* 0xAA - Bit synchronization pulse train */
    uint8_t sync_word;   /* 0xD5 - Frame start delimiter */
    uint8_t node_id;     /* Transmitting Bamboo Node ID (1-255) */
    uint8_t seq_num;     /* Monotonic sequence counter */
    uint8_t state_byte;  /* 8-bit discrete state vector */
    uint8_t crc8;        /* CRC-8-CCITT checksum over node_id, seq_num, state_byte */
} neuron_wire_frame_t;
#pragma pack(pop)

/**
 * Pack discrete state components into a single 8-bit state vector.
 */
static inline uint8_t neuron_pack_state(
    neuron_mode_t mode,
    neuron_lock_status_t lock,
    bool consensus_ack,
    bool proximity_alert,
    bool swap_critical,
    bool sync_marker
) {
    uint8_t state = 0;
    state |= ((uint8_t)mode & 0x03) << NEURON_STATE_MODE_SHIFT;
    state |= ((uint8_t)lock & 0x03) << NEURON_STATE_LOCK_SHIFT;
    if (consensus_ack)    state |= NEURON_STATE_CONSENSUS_ACK;
    if (proximity_alert)  state |= NEURON_STATE_PROXIMITY_ALERT;
    if (swap_critical)    state |= NEURON_STATE_SWAP_CRITICAL;
    if (sync_marker)      state |= NEURON_STATE_SYNC_MARKER;
    return state;
}

/**
 * Unpack 8-bit discrete state vector into individual fields.
 */
static inline void neuron_unpack_state(
    uint8_t state,
    neuron_mode_t *out_mode,
    neuron_lock_status_t *out_lock,
    bool *out_consensus_ack,
    bool *out_proximity_alert,
    bool *out_swap_critical,
    bool *out_sync_marker
) {
    if (out_mode)            *out_mode = (neuron_mode_t)((state & NEURON_STATE_MODE_MASK) >> NEURON_STATE_MODE_SHIFT);
    if (out_lock)            *out_lock = (neuron_lock_status_t)((state & NEURON_STATE_LOCK_MASK) >> NEURON_STATE_LOCK_SHIFT);
    if (out_consensus_ack)   *out_consensus_ack = (state & NEURON_STATE_CONSENSUS_ACK) != 0;
    if (out_proximity_alert) *out_proximity_alert = (state & NEURON_STATE_PROXIMITY_ALERT) != 0;
    if (out_swap_critical)   *out_swap_critical = (state & NEURON_STATE_SWAP_CRITICAL) != 0;
    if (out_sync_marker)     *out_sync_marker = (state & NEURON_STATE_SYNC_MARKER) != 0;
}

/**
 * Deterministic CRC-8-CCITT calculation (Polynomial 0x07, Initial 0x00).
 * Bounded latency, zero memory allocation, constant execution time per byte.
 */
static inline uint8_t neuron_crc8_update(uint8_t crc, uint8_t data) {
    crc ^= data;
    for (uint8_t bit = 0; bit < 8; ++bit) {
        if (crc & 0x80) {
            crc = (uint8_t)((crc << 1) ^ 0x07);
        } else {
            crc = (uint8_t)(crc << 1);
        }
    }
    return crc;
}

/**
 * Calculate CRC-8 over a buffer.
 */
static inline uint8_t neuron_crc8(const uint8_t *data, uint8_t len) {
    uint8_t crc = 0x00;
    for (uint8_t i = 0; i < len; ++i) {
        crc = neuron_crc8_update(crc, data[i]);
    }
    return crc;
}

/**
 * Initialize a wire frame with preamble, sync word, payload, and calculated CRC-8.
 */
static inline void neuron_frame_init(
    neuron_wire_frame_t *frame,
    uint8_t node_id,
    uint8_t seq_num,
    uint8_t state_byte
) {
    frame->preamble   = NEURON_WIRE_PREAMBLE;
    frame->sync_word  = NEURON_WIRE_SYNC_WORD;
    frame->node_id    = node_id;
    frame->seq_num    = seq_num;
    frame->state_byte = state_byte;

    /* Calculate CRC over payload: node_id, seq_num, state_byte */
    const uint8_t payload[3] = { node_id, seq_num, state_byte };
    frame->crc8 = neuron_crc8(payload, 3);
}

/**
 * Validate received wire frame integrity.
 * Returns true if preamble, sync word, and CRC-8 match.
 */
static inline bool neuron_frame_validate(const neuron_wire_frame_t *frame) {
    if (frame->preamble != NEURON_WIRE_PREAMBLE) return false;
    if (frame->sync_word != NEURON_WIRE_SYNC_WORD) return false;
    
    const uint8_t payload[3] = { frame->node_id, frame->seq_num, frame->state_byte };
    uint8_t expected_crc = neuron_crc8(payload, 3);
    return frame->crc8 == expected_crc;
}

#ifdef __cplusplus
}
#endif

#endif /* NEURON_WIRE_H */
