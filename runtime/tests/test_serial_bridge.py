"""Unit tests for Panda Runtime deterministic serial hardware bridge."""

import unittest
import proto.neuron_wire as nw
from runtime.panda.serial_bridge import SerialBridge


class TestSerialBridge(unittest.TestCase):
    def setUp(self):
        self.bridge = SerialBridge(port="/dev/ttyAMA0", simulate=True)

    def tearDown(self):
        self.bridge.close()

    def test_send_valid_frame(self):
        state = nw.pack_state(nw.MODE_FORMATION_LOCK, nw.LOCK_HARD_LOCKED, consensus_ack=True)
        frame_bytes = nw.pack_frame(node_id=1, seq_num=10, state_byte=state)
        self.assertEqual(len(frame_bytes), 6)

        success = self.bridge.send_wire_frame(frame_bytes)
        self.assertTrue(success)
        self.assertEqual(len(self.bridge.simulated_tx_queue), 1)
        self.assertEqual(self.bridge.simulated_tx_queue[0], frame_bytes)

    def test_reject_invalid_frame_length(self):
        bad_frame = b"\xAA\xD5\x01" # Only 3 bytes
        success = self.bridge.send_wire_frame(bad_frame)
        self.assertFalse(success)
        self.assertEqual(len(self.bridge.simulated_tx_queue), 0)

    def test_read_wire_frame_with_crc_validation(self):
        state = nw.pack_state(nw.MODE_DISPERSAL, nw.LOCK_NONE, proximity_alert=True)
        frame_bytes = nw.pack_frame(node_id=5, seq_num=99, state_byte=state)

        # Inject into simulated RX queue
        self.bridge.simulated_rx_queue.append(frame_bytes)

        wf = self.bridge.read_wire_frame()
        self.assertIsNotNone(wf)
        self.assertEqual(wf.node_id, 5)
        self.assertEqual(wf.seq_num, 99)
        self.assertEqual(wf.state.mode, nw.MODE_DISPERSAL)
        self.assertTrue(wf.state.proximity_alert)


if __name__ == "__main__":
    unittest.main()
