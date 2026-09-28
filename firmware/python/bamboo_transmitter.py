"""MicroPython / Bench test driver for RP2040 Bamboo Node optical transmitter.

Provides direct GPIO bit-banging with microsecond precision for Manchester
encoded 850nm IR pulses. Compatible with MicroPython on Raspberry Pi Pico.
"""

import time
import sys

try:
    from machine import Pin
    IS_MICROPYTHON = True
except ImportError:
    IS_MICROPYTHON = False

import proto.neuron_wire as nw


class MockPin:
    def __init__(self, pin_id):
        self.pin_id = pin_id
        self.val = 0

    def value(self, v=None):
        if v is not None:
            self.val = 1 if v else 0
        return self.val


class BambooTransmitter:
    def __init__(self, gpio_pin=15, baud_rate=1000):
        self.baud_rate = baud_rate
        self.half_bit_us = int(1_000_000 / (2 * baud_rate))
        self.seq_num = 0

        if IS_MICROPYTHON:
            self.pin = Pin(gpio_pin, Pin.OUT)
            self.pin.value(0)
        else:
            self.pin = MockPin(gpio_pin)

    def transmit_frame(self, node_id: int, state_byte: int) -> int:
        frame_bytes = nw.pack_frame(node_id, self.seq_num, state_byte)
        self.seq_num = (self.seq_num + 1) & 0xFF

        # Manchester encode IEEE 802.3
        chips = []
        for b in frame_bytes:
            for bit_pos in range(7, -1, -1):
                bit = (b >> bit_pos) & 1
                if bit == 0:
                    chips.extend([1, 0])
                else:
                    chips.extend([0, 1])

        # Transmit chips
        if IS_MICROPYTHON:
            import time
            for chip in chips:
                self.pin.value(chip)
                time.sleep_us(self.half_bit_us)
            self.pin.value(0)
        else:
            # Host simulation
            for chip in chips:
                self.pin.value(chip)
            self.pin.value(0)

        return len(chips)


if __name__ == "__main__":
    tx = BambooTransmitter(gpio_pin=15, baud_rate=1000)
    state = nw.pack_state(
        nw.MODE_FORMATION_LOCK,
        nw.LOCK_HARD_LOCKED,
        consensus_ack=True,
        swap_critical=False,
    )
    chips_sent = tx.transmit_frame(node_id=1, state_byte=state)
    print(f"INFO: Bamboo Node 1 optical transmission complete. Chips emitted: {chips_sent}")
