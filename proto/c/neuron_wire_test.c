#include <stdio.h>
#include <assert.h>
#include "neuron_wire.h"

int main(void) {
    /* Test 1: Frame size must be exactly 6 bytes (48 bits) */
    assert(sizeof(neuron_wire_frame_t) == 6);
    printf("CHECK: sizeof(neuron_wire_frame_t) == 6 bytes [OK]\n");

    /* Test 2: State packing and unpacking */
    neuron_mode_t mode = NEURON_MODE_FORMATION_LOCK;
    neuron_lock_status_t lock = NEURON_LOCK_HARD_LOCKED;
    bool consensus_ack = true;
    bool proximity_alert = false;
    bool swap_critical = true;
    bool sync_marker = false;

    uint8_t packed_state = neuron_pack_state(
        mode, lock, consensus_ack, proximity_alert, swap_critical, sync_marker
    );

    /* Verify bit values:
       mode = 2 (0b10)
       lock = 3 (0b11) -> << 2 = 0b1100 (0x0C)
       consensus_ack = true -> 0x10
       proximity = false -> 0x00
       swap_critical = true -> 0x40
       sync_marker = false -> 0x00
       Total: 0x02 | 0x0C | 0x10 | 0x40 = 0x5E
    */
    assert(packed_state == 0x5E);
    printf("CHECK: Packed state byte = 0x%02X [OK]\n", packed_state);

    neuron_mode_t out_mode;
    neuron_lock_status_t out_lock;
    bool out_consensus_ack, out_proximity_alert, out_swap_critical, out_sync_marker;

    neuron_unpack_state(
        packed_state,
        &out_mode, &out_lock,
        &out_consensus_ack, &out_proximity_alert,
        &out_swap_critical, &out_sync_marker
    );

    assert(out_mode == NEURON_MODE_FORMATION_LOCK);
    assert(out_lock == NEURON_LOCK_HARD_LOCKED);
    assert(out_consensus_ack == true);
    assert(out_proximity_alert == false);
    assert(out_swap_critical == true);
    assert(out_sync_marker == false);
    printf("CHECK: State unpacking roundtrip [OK]\n");

    /* Test 3: Frame initialization and CRC-8 validation */
    neuron_wire_frame_t frame;
    neuron_frame_init(&frame, 42, 100, packed_state);

    assert(frame.preamble == NEURON_WIRE_PREAMBLE);
    assert(frame.sync_word == NEURON_WIRE_SYNC_WORD);
    assert(frame.node_id == 42);
    assert(frame.seq_num == 100);
    assert(frame.state_byte == packed_state);
    assert(neuron_frame_validate(&frame) == true);
    printf("CHECK: Frame initialized and validated with CRC-8=0x%02X [OK]\n", frame.crc8);

    /* Test 4: Corruption detection via CRC-8 */
    frame.state_byte ^= 0x01; /* Corrupt 1 bit */
    assert(neuron_frame_validate(&frame) == false);
    printf("CHECK: Single-bit corruption rejected by CRC-8 [OK]\n");

    printf("ALL TESTS PASSED.\n");
    return 0;
}
