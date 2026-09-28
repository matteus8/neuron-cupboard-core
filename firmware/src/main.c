/**
 * @file main.c
 * @brief Bamboo Node optical transmitter firmware entry point for RP2040.
 *
 * Runs on Raspberry Pi Pico / RP2040. Emits periodic 850nm IR Manchester
 * pulse trains over GPIO 15 to announce node state and consensus flags to the swarm.
 */

#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>

#include "../include/manchester.h"
#include "../../proto/c/neuron_wire.h"

#ifdef PICO_BOARD
#include "pico/stdlib.h"
#include "hardware/timer.h"
#include "hardware/gpio.h"

static void pico_gpio_write(uint8_t pin, bool high) {
    gpio_put(pin, high);
}

static void pico_delay_us(uint32_t us) {
    sleep_us(us);
}
#else
/* Host stub / simulation harness */
static void pico_gpio_write(uint8_t pin, bool high) {
    (void)pin; (void)high;
}

static void pico_delay_us(uint32_t us) {
    (void)us;
}
#endif

#define BAMBOO_TX_PIN         15    /* GPIO 15 driving IR LED FET */
#define BAMBOO_NODE_ID        1     /* Default Bamboo Node ID */
#define BEACON_INTERVAL_MS    100   /* 10 Hz state beacon transmission */

int main(void) {
#ifdef PICO_BOARD
    stdio_init_all();
    gpio_init(BAMBOO_TX_PIN);
    gpio_set_dir(BAMBOO_TX_PIN, GPIO_OUT);
    gpio_put(BAMBOO_TX_PIN, 0);
#endif

    manchester_tx_t tx;
    manchester_tx_init(&tx, BAMBOO_TX_PIN, 1000, MANCHESTER_POLARITY_IEEE8023);

    uint8_t seq_num = 0;
    neuron_wire_frame_t frame;

    while (1) {
        /* Pack discrete state vector */
        uint8_t state = neuron_pack_state(
            NEURON_MODE_FORMATION_LOCK,
            NEURON_LOCK_HARD_LOCKED,
            true,   /* Consensus ACK */
            false,  /* Proximity alert */
            false,  /* SWaP critical */
            false   /* Sync marker */
        );

        neuron_frame_init(&frame, BAMBOO_NODE_ID, seq_num++, state);

        /* Encode frame to Manchester chips */
        manchester_encode_frame(&tx, &frame);

        /* Transmit optical pulse train with microsecond precision */
        manchester_tx_transmit_blocking(&tx, pico_gpio_write, pico_delay_us);

#ifdef PICO_BOARD
        sleep_ms(BEACON_INTERVAL_MS);
#else
        break; /* Exit simulation */
#endif
    }

    return 0;
}
