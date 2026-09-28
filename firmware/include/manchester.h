/**
 * @file manchester.h
 * @brief Deterministic Manchester encoder and optical pulse generator for RP2040.
 *
 * Implements physical-layer optical modulation for the 850nm IR emitter.
 * Operates with zero dynamic allocations using hardware timer interrupts or
 * microsecond busy-loops on ARM Cortex-M0+.
 */

#ifndef MANCHESTER_H
#define MANCHESTER_H

#include <stdint.h>
#include <stdbool.h>
#include "../../proto/c/neuron_wire.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Default physical optical configuration */
#define MANCHESTER_DEFAULT_BAUD_RATE   (1000)                   /* 1000 symbols/sec */
#define MANCHESTER_HALF_BIT_US         (500)                    /* 500 microseconds per half-bit */
#define MANCHESTER_FRAME_MAX_BITS      (NEURON_WIRE_FRAME_LEN * 8) /* 48 bits */
#define MANCHESTER_MAX_CHIPS           (MANCHESTER_FRAME_MAX_BITS * 2) /* 96 half-bit chips */

/**
 * Manchester bit polarity convention:
 * IEEE 802.3:
 *   Bit 0: HIGH -> LOW  (Chip 1 then Chip 0)
 *   Bit 1: LOW  -> HIGH (Chip 0 then Chip 1)
 */
typedef enum {
    MANCHESTER_POLARITY_IEEE8023 = 0,
    MANCHESTER_POLARITY_THOMAS   = 1
} manchester_polarity_t;

/**
 * Static transmitter context (no heap allocations).
 */
typedef struct {
    uint8_t tx_pin;                           /* Hardware GPIO pin connected to 850nm IR LED FET driver */
    uint16_t half_bit_us;                     /* Half-bit pulse duration in microseconds */
    manchester_polarity_t polarity;           /* Encoding polarity convention */
    uint8_t chip_buffer[MANCHESTER_MAX_CHIPS];/* Pre-encoded half-bit chip sequence */
    uint16_t chip_count;                      /* Total half-bits to transmit */
    uint16_t current_chip;                    /* Current transmission index */
    bool is_transmitting;                     /* Transmission in progress flag */
} manchester_tx_t;

/**
 * Initialize transmitter context.
 */
void manchester_tx_init(manchester_tx_t *tx, uint8_t gpio_pin, uint16_t baud_rate, manchester_polarity_t polarity);

/**
 * Encode a raw byte buffer into Manchester half-bit chips.
 * Returns total number of chips generated (len * 16).
 */
uint16_t manchester_encode_bytes(manchester_tx_t *tx, const uint8_t *data, uint8_t len);

/**
 * Encode a complete 6-byte Neuron wire frame into the transmitter buffer.
 */
uint16_t manchester_encode_frame(manchester_tx_t *tx, const neuron_wire_frame_t *frame);

/**
 * Transmit pre-encoded chips over GPIO with microsecond timing.
 * Platform-agnostic prototype (invokes gpio_set and delay_us callbacks).
 */
typedef void (*gpio_write_fn)(uint8_t pin, bool high);
typedef void (*delay_us_fn)(uint32_t us);

void manchester_tx_transmit_blocking(
    manchester_tx_t *tx,
    gpio_write_fn write_pin,
    delay_us_fn delay_us
);

#ifdef __cplusplus
}
#endif

#endif /* MANCHESTER_H */
