"""Unit tests for Panda Runtime Manchester Optical Pulse Decoder."""

import unittest
import proto.neuron_wire as nw
from runtime.panda.decoder import ManchesterDecoder


class TestManchesterDecoder(unittest.TestCase):
    def setUp(self):
        self.decoder = ManchesterDecoder(polarity=0) # IEEE 802.3

    def test_single_byte_decode(self):
        # Bit 0 -> (1, 0); Bit 1 -> (0, 1)
        # Byte 0xAA = 10101010b -> (0,1), (1,0), (0,1), (1,0), (0,1), (1,0), (0,1), (1,0)
        chips = [0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0]
        decoded_bits = []
        for c in chips:
            b = self.decoder.feed_chip(c)
            if b is not None:
                decoded_bits.append(b)

        self.assertEqual(len(decoded_bits), 8)
        self.assertEqual(decoded_bits, [1, 0, 1, 0, 1, 0, 1, 0])
        byte_val = self.decoder._bits_to_byte(decoded_bits)
        self.assertEqual(byte_val, 0xAA)

    def test_full_frame_decode(self):
        # Pack state: Formation lock, hard locked, consensus ACK
        state_byte = nw.pack_state(
            nw.MODE_FORMATION_LOCK,
            nw.LOCK_HARD_LOCKED,
            consensus_ack=True,
            swap_critical=False,
        )
        frame_bytes = nw.pack_frame(node_id=7, seq_num=42, state_byte=state_byte)
        self.assertEqual(len(frame_bytes), 6)

        # Convert frame bytes to IEEE 802.3 Manchester chips
        chips = []
        for b in frame_bytes:
            for bit_pos in range(7, -1, -1):
                bit = (b >> bit_pos) & 1
                if bit == 0:
                    chips.extend([1, 0])
                else:
                    chips.extend([0, 1])

        self.assertEqual(len(chips), 96)

        # Feed chips into decoder
        frames = self.decoder.feed_chips(chips)
        self.assertEqual(len(frames), 1)

        f = frames[0]
        self.assertEqual(f.node_id, 7)
        self.assertEqual(f.seq_num, 42)
        self.assertEqual(f.state_byte, state_byte)
        self.assertEqual(f.state.mode, nw.MODE_FORMATION_LOCK)
        self.assertEqual(f.state.lock_status, nw.LOCK_HARD_LOCKED)
        self.assertTrue(f.state.consensus_ack)
        self.assertFalse(f.state.swap_critical)

    def test_noise_and_corruption_rejection(self):
        # Inject random noise chips
        noise = [1, 1, 0, 0, 1, 1, 1, 0]
        frames = self.decoder.feed_chips(noise)
        self.assertEqual(len(frames), 0)


if __name__ == "__main__":
    unittest.main()
