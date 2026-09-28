#include <stdio.h>
#include <assert.h>
#include "../include/bamboo_pio.h"
#include "../include/manchester.h"

int main(void) {
    neuron_wire_frame_t frame;
    uint8_t state = neuron_pack_state(NEURON_MODE_FORMATION_LOCK, NEURON_LOCK_HARD_LOCKED, true, false, false, false);
    neuron_frame_init(&frame, 42, 100, state);

    // 1. Pack using bamboo_pio
    uint32_t pio_words[BAMBOO_PIO_WORDS_PER_FRAME];
    bamboo_pio_pack_frame(&frame, pio_words);

    // 2. Encode using standard manchester_tx
    manchester_tx_t tx;
    manchester_tx_init(&tx, 15, 1000, MANCHESTER_POLARITY_IEEE8023);
    uint16_t chip_count = manchester_encode_frame(&tx, &frame);
    assert(chip_count == 96);

    // 3. Verify exact 1-to-1 chip equality across all 96 chips
    for (int word_idx = 0; word_idx < BAMBOO_PIO_WORDS_PER_FRAME; ++word_idx) {
        uint32_t w = pio_words[word_idx];
        for (int b = 31; b >= 0; --b) {
            uint8_t pio_chip = (w >> b) & 1;
            int chip_index = (word_idx * 32) + (31 - b);
            assert(pio_chip == tx.chip_buffer[chip_index]);
        }
    }

    printf("CHECK: PIO 3-word packing matches 96 Manchester chips exactly [OK]\n");
    printf("Word 0: 0x%08X\n", pio_words[0]);
    printf("Word 1: 0x%08X\n", pio_words[1]);
    printf("Word 2: 0x%08X\n", pio_words[2]);
    printf("ALL BAMBOO PIO TESTS PASSED.\n");
    return 0;
}
