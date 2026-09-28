/**
 * @file bamboo_pio.h
 * @brief RP2040 PIO Hardware Transmitter Driver for Bamboo Node Optical Link.
 *
 * Packs 96 Manchester chips (48 bits from a 6-byte Neuron wire frame) into
 * exactly three 32-bit words and streams them through the RP2040 PIO FIFO.
 */

#ifndef BAMBOO_PIO_H
#define BAMBOO_PIO_H

#include <stdint.h>
#include <stdbool.h>
#include "../../proto/c/neuron_wire.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BAMBOO_PIO_WORDS_PER_FRAME  (3) /* 96 chips / 32 bits = 3 words */

/**
 * Pack a 6-byte Neuron frame into three 32-bit PIO FIFO words.
 * Encodes using IEEE 802.3 Manchester polarity (MSB first).
 *
 * @param frame Pointer to validated 6-byte wire frame.
 * @param out_words Array of 3 uint32_t words ready for PIO FIFO.
 */
static inline void bamboo_pio_pack_frame(
    const neuron_wire_frame_t *frame,
    uint32_t out_words[BAMBOO_PIO_WORDS_PER_FRAME]
) {
    const uint8_t *bytes = (const uint8_t *)frame;
    uint32_t current_word = 0;
    uint8_t bits_in_word = 0;
    uint8_t word_idx = 0;

    for (uint8_t b = 0; b < NEURON_WIRE_FRAME_LEN; ++b) {
        uint8_t byte_val = bytes[b];

        for (int8_t bit_pos = 7; bit_pos >= 0; --bit_pos) {
            uint8_t bit = (byte_val >> bit_pos) & 1;

            // IEEE 802.3: bit 0 -> (1, 0); bit 1 -> (0, 1)
            uint8_t c1 = (bit == 0) ? 1 : 0;
            uint8_t c2 = (bit == 0) ? 0 : 1;

            current_word = (current_word << 1) | c1;
            current_word = (current_word << 1) | c2;
            bits_in_word += 2;

            if (bits_in_word == 32) {
                out_words[word_idx++] = current_word;
                current_word = 0;
                bits_in_word = 0;
            }
        }
    }
}

#ifdef __cplusplus
}
#endif

#endif /* BAMBOO_PIO_H */
