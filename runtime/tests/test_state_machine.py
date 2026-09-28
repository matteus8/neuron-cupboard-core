"""Unit tests for Panda Runtime autonomous swarm state machine."""

import unittest
from runtime.panda.cupboard import TheCupboard
from runtime.panda.state_machine import SwarmStateMachine
import proto.neuron_wire as nw


class TestSwarmStateMachine(unittest.TestCase):
    def setUp(self):
        self.cupboard = TheCupboard(node_timeout_us=1_000_000)
        self.sm = SwarmStateMachine(node_id=1, cupboard=self.cupboard, min_lock_frames=2)

    def test_initial_search_mode(self):
        decision = self.sm.evaluate_tick()
        self.assertEqual(decision.mode, nw.MODE_SEARCH)
        self.assertEqual(decision.lock_status, nw.LOCK_NONE)
        self.assertFalse(decision.consensus_ack)

    def test_acquiring_to_tracking_progression(self):
        # Neighbor 2 appears
        s2 = nw.pack_state(nw.MODE_SEARCH, nw.LOCK_NONE)
        self.cupboard.update_node(node_id=2, seq_num=1, state_byte=s2)

        # Frame 1: ACQUIRING
        d1 = self.sm.evaluate_tick()
        self.assertEqual(d1.lock_status, nw.LOCK_ACQUIRING)
        self.assertEqual(d1.mode, nw.MODE_SEARCH)

        # Frame 2: TRACKING
        d2 = self.sm.evaluate_tick()
        self.assertEqual(d2.lock_status, nw.LOCK_TRACKING)

    def test_consensus_and_hard_lock_formation(self):
        # Neighbor 2 is already tracking and acknowledges consensus
        s2 = nw.pack_state(nw.MODE_SEARCH, nw.LOCK_TRACKING, consensus_ack=True)
        self.cupboard.update_node(node_id=2, seq_num=10, state_byte=s2)

        # Tick 1: acquiring
        self.sm.evaluate_tick()
        # Tick 2: tracking & neighbor has consensus ACK -> HARD_LOCKED + FORMATION_LOCK
        d = self.sm.evaluate_tick()
        self.assertEqual(d.lock_status, nw.LOCK_HARD_LOCKED)
        self.assertEqual(d.mode, nw.MODE_FORMATION_LOCK)
        self.assertTrue(d.consensus_ack)

    def test_proximity_alert_forces_dispersal(self):
        # Neighbor 2 alerts collision
        s2 = nw.pack_state(nw.MODE_FORMATION_LOCK, nw.LOCK_HARD_LOCKED, proximity_alert=True)
        self.cupboard.update_node(node_id=2, seq_num=12, state_byte=s2)

        d = self.sm.evaluate_tick()
        self.assertEqual(d.mode, nw.MODE_DISPERSAL)
        self.assertTrue(d.proximity_alert)
        self.assertFalse(d.consensus_ack)


if __name__ == "__main__":
    unittest.main()
