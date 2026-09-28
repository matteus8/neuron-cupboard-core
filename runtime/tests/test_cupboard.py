"""Unit tests for The Cupboard swarm consensus engine."""

import unittest
from runtime.panda.cupboard import TheCupboard
import proto.neuron_wire as nw


class TestTheCupboard(unittest.TestCase):
    def setUp(self):
        # 500ms timeout for test
        self.cupboard = TheCupboard(node_timeout_us=500_000)

    def test_node_lifecycle_and_consensus(self):
        # State: Node 1 Formation Lock + ACK
        s1 = nw.pack_state(nw.MODE_FORMATION_LOCK, nw.LOCK_HARD_LOCKED, consensus_ack=True)
        # State: Node 2 Formation Lock + ACK
        s2 = nw.pack_state(nw.MODE_FORMATION_LOCK, nw.LOCK_HARD_LOCKED, consensus_ack=True)

        t0 = 1_000_000
        self.cupboard.update_node(node_id=1, seq_num=10, state_byte=s1, timestamp_us=t0)
        self.cupboard.update_node(node_id=2, seq_num=20, state_byte=s2, timestamp_us=t0)

        self.assertEqual(self.cupboard.active_node_count, 2)
        self.assertTrue(self.cupboard.is_consensus_reached())

        # Node 1 reports proximity alert
        s1_alert = nw.pack_state(nw.MODE_FORMATION_LOCK, nw.LOCK_HARD_LOCKED, proximity_alert=True)
        self.cupboard.update_node(node_id=1, seq_num=11, state_byte=s1_alert, timestamp_us=t0 + 100_000)
        self.assertEqual(self.cupboard.get_proximity_alerts(), [1])

        # Eviction test: advance time by 550ms (beyond 500ms timeout for node 2 at t0, but within node 1 at t0+100ms)
        evicted = self.cupboard.evict_stale_nodes(current_time_us=t0 + 550_000)
        self.assertEqual(evicted, [2])
        self.assertEqual(self.cupboard.active_node_count, 1)


if __name__ == "__main__":
    unittest.main()
