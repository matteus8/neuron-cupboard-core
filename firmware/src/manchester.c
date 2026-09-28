/**
 * @file manchester.c
 * @brief Deterministic Manchester encoder and optical pulse generator implementation.
 */

#include "../include/manchester.h"
#include <string.h>

void manchester_tx_init(manchester_tx_t *tx, uint8_t gpio_pin, uint16_t baud_rate, manchester_polarity_t polarity) {
    if (!tx) return;
    tx->tx_pin = gpio_pin;
    tx->polarity = polarity;
    if (baud_rate == 0) baud_rate = MANCHESTER_DEFAULT_BAUD_RATE;
    /* Half-bit time = 1,000,000 / (2 * baud_rate) */
    tx->half_bit_us = (uint16_t)(1000000UL / (2UL * baud_rate));
    tx->chip_count = 0;
    tx->current_chip = 0;
    tx->is_transmitting = false;
    memset(tx->chip_buffer, 0, sizeof(tx->chip_buffer));
}

uint16_t manchester_encode_bytes(manchester_tx_t *tx, const uint8_t *data, uint8_t len) {
    if (!tx || !data || len == 0) return 0;

    uint16_t chip_idx = 0;
    for (uint8_t byte_idx = 0; byte_idx < len; ++byte_idx) {
        uint8_t current_byte = data[byte_idx];

        /* Encode 8 bits, MSB first */
        for (int8_t bit_pos = 7; bit_pos >= 0; --bit_pos) {
            if (chip_idx + 1 >= MANCHESTER_MAX_CHIPS) break;

            uint8_t bit = (current_byte >> bit_pos) & 0x01;

            if (tx->polarity == MANCHESTER_POLARITY_IEEE8023) {
                /* IEEE 802.3: 0 -> High-Low (1, 0); 1 -> Low-High (0, 1) */
                tx->chip_buffer[chip_idx++] = (bit == 0) ? 1 : 0;
                tx->chip_buffer[chip_idx++] = (bit == 0) ? 0 : 1;
            } else {
                /* G.E. Thomas: 0 -> Low-High (0, 1); 1 -> High-Low (1, 0) */
                tx->chip_buffer[chip_idx++] = (bit == 0) ? 0 : 1;
                tx->chip_buffer[chip_idx++] = (bit == 0) ? 1 : 0;
            }
        }
    }

    tx->chip_count = chip_idx;
    tx->current_chip = 0;
    return chip_idx;
}

uint16_t manchester_encode_frame(manchester_tx_t *tx, const neuron_wire_frame_t *frame) {
    if (!tx || !frame) return 0;
    return manchester_encode_bytes(tx, (const uint8_t *)frame, NEURON_WIRE_FRAME_LEN);
}

void manchester_tx_transmit_blocking(
    manchester_tx_t *tx,
    gpio_write_fn write_pin,
    delay_us_fn delay_us
) {
    if (!tx || !write_pin || !delay_us || tx->chip_count == 0) return;

    tx->is_transmitting = true;

    for (uint16_t i = 0; i < tx->chip_count; ++i) {
        write_pin(tx->tx_pin, tx->chip_buffer[i] != 0);
        delay_us(tx->half_bit_us);
    }

    /* Return pin to idle low after transmission */
    write_pin(tx->tx_pin, false);
    tx->is_transmitting = false;
}
