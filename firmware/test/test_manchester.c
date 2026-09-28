#include <stdio.h>
#include <assert.h>
#include "../include/manchester.h"

static uint8_t mock_gpio_state = 0;
static uint32_t mock_total_delay_us = 0;

static void mock_gpio_write(uint8_t pin, bool high) {
    (void)pin;
    mock_gpio_state = high ? 1 : 0;
}

static void mock_delay_us(uint32_t us) {
    mock_total_delay_us += us;
}

int main(void) {
    manchester_tx_t tx;
    manchester_tx_init(&tx, 15, 1000, MANCHESTER_POLARITY_IEEE8023);

    assert(tx.half_bit_us == 500);
    printf("CHECK: Half-bit delay calculated to %u us [OK]\n", tx.half_bit_us);

    /* Test single byte encoding */
    uint8_t test_byte = 0xAA; /* 10101010b */
    uint16_t chips = manchester_encode_bytes(&tx, &test_byte, 1);
    assert(chips == 16);

    /* For IEEE 802.3:
       Bit 1 -> Low then High (0, 1)
       Bit 0 -> High then Low (1, 0)
       0xAA = 1, 0, 1, 0, 1, 0, 1, 0
       Chips: (0,1), (1,0), (0,1), (1,0), (0,1), (1,0), (0,1), (1,0)
    */
    uint8_t expected_chips[16] = {0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0};
    for (int i = 0; i < 16; ++i) {
        assert(tx.chip_buffer[i] == expected_chips[i]);
    }
    printf("CHECK: Manchester bit pattern matches IEEE 802.3 specification [OK]\n");

    /* Test full frame encoding */
    neuron_wire_frame_t frame;
    uint8_t state = neuron_pack_state(NEURON_MODE_FORMATION_LOCK, NEURON_LOCK_HARD_LOCKED, true, false, true, false);
    neuron_frame_init(&frame, 42, 1, state);

    uint16_t frame_chips = manchester_encode_frame(&tx, &frame);
    assert(frame_chips == 96); /* 6 bytes * 8 bits * 2 chips = 96 */
    printf("CHECK: Full 6-byte Neuron wire frame encoded into %u chips [OK]\n", frame_chips);

    /* Test mock transmission */
    mock_total_delay_us = 0;
    manchester_tx_transmit_blocking(&tx, mock_gpio_write, mock_delay_us);
    assert(mock_total_delay_us == 96 * 500); /* 48,000 us = 48 ms */
    assert(mock_gpio_state == 0); /* Idle low after transmission */
    printf("CHECK: Mock transmission completed in %u us (48ms) with idle low [OK]\n", mock_total_delay_us);

    printf("ALL FIRMWARE MANCHESTER TESTS PASSED.\n");
    return 0;
}
