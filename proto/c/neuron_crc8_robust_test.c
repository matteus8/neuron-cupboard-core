/**
 * @file neuron_crc8_robust_test.c
 * @brief Mathematical and empirical verification of CRC-8 error detection capabilities.
 *
 * Verifies that the polynomial 0x07 with initial value 0x00 achieves:
 * 1. 100% detection of all single-bit corruptions across the entire 48-bit frame.
 * 2. 100% detection of all double-bit corruptions across payload and header.
 * 3. 100% detection of common burst error syndromes.
 */

#include <stdio.h>
#include <assert.h>
#include <string.h>
#include "neuron_wire.h"

int main(void) {
    printf("==> Running Exhaustive CRC-8 Mathematical Robustness Suite...\n");

    neuron_wire_frame_t valid_frame;
    uint8_t state = neuron_pack_state(NEURON_MODE_FORMATION_LOCK, NEURON_LOCK_HARD_LOCKED, true, false, true, false);
    neuron_frame_init(&valid_frame, 42, 100, state);
    assert(neuron_frame_validate(&valid_frame) == true);

    const size_t total_bits = sizeof(neuron_wire_frame_t) * 8; // 48 bits

    /* Test 1: Exhaustive Single-Bit Error Detection (48 / 48) */
    size_t single_bit_tested = 0;
    size_t single_bit_detected = 0;

    for (size_t bit = 0; bit < total_bits; ++bit) {
        neuron_wire_frame_t corrupted = valid_frame;
        uint8_t *corrupted_bytes = (uint8_t *)&corrupted;

        corrupted_bytes[bit / 8] ^= (1 << (bit % 8));
        single_bit_tested++;

        if (!neuron_frame_validate(&corrupted)) {
            single_bit_detected++;
        }
    }

    assert(single_bit_tested == 48);
    assert(single_bit_detected == 48);
    printf("  [PASS] Single-bit corruption detection: 48/48 (100.0%%)\n");

    /* Test 2: Exhaustive Double-Bit Error Detection (1,128 combinations) */
    size_t double_bit_tested = 0;
    size_t double_bit_detected = 0;

    for (size_t b1 = 0; b1 < total_bits; ++b1) {
        for (size_t b2 = b1 + 1; b2 < total_bits; ++b2) {
            neuron_wire_frame_t corrupted = valid_frame;
            uint8_t *corrupted_bytes = (uint8_t *)&corrupted;

            corrupted_bytes[b1 / 8] ^= (1 << (b1 % 8));
            corrupted_bytes[b2 / 8] ^= (1 << (b2 % 8));
            double_bit_tested++;

            if (!neuron_frame_validate(&corrupted)) {
                double_bit_detected++;
            }
        }
    }

    // 48 * 47 / 2 = 1128 combinations
    assert(double_bit_tested == 1128);
    assert(double_bit_detected == 1128);
    printf("  [PASS] Double-bit corruption detection: 1128/1128 (100.0%%)\n");

    /* Test 3: Burst Error Detection (lengths 2 to 7 bits) */
    size_t burst_tested = 0;
    size_t burst_detected = 0;

    for (size_t burst_len = 2; burst_len <= 7; ++burst_len) {
        for (size_t start_bit = 0; start_bit + burst_len < total_bits; ++start_bit) {
            neuron_wire_frame_t corrupted = valid_frame;
            uint8_t *corrupted_bytes = (uint8_t *)&corrupted;

            for (size_t i = 0; i < burst_len; ++i) {
                size_t b = start_bit + i;
                corrupted_bytes[b / 8] ^= (1 << (b % 8));
            }
            burst_tested++;
            if (!neuron_frame_validate(&corrupted)) {
                burst_detected++;
            }
        }
    }

    assert(burst_detected == burst_tested);
    printf("  [PASS] Burst corruption detection (length 2-7): %zu/%zu (100.0%%)\n", burst_detected, burst_tested);

    /* Test 4: Extreme Boundary Patterns */
    uint8_t boundary_states[] = {0x00, 0xFF, 0xAA, 0x55, 0x0F, 0xF0};
    for (size_t i = 0; i < sizeof(boundary_states); ++i) {
        neuron_wire_frame_t bf;
        neuron_frame_init(&bf, boundary_states[i], boundary_states[i], boundary_states[i]);
        assert(neuron_frame_validate(&bf) == true);
    }
    printf("  [PASS] Boundary patterns (0x00, 0xFF, 0xAA, 0x55, 0x0F, 0xF0) verified\n");

    printf("ALL CRC-8 ROBUSTNESS TESTS PASSED.\n");
    return 0;
}
