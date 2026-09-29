"""Swarm Scaling, Byzantine Conflict, and Quorum Stress Test Suite.

Stress tests:
1. Swarm scaling to 6+ simultaneous Bamboo Nodes.
2. Immediate preemption of Formation Lock upon any node Proximity / Anti-Collision Alert.
3. Monotonic epoch advancement and staggered TTL timeout evictions.
"""

import unittest
import proto.neuron_wire as nw
from runtime.panda.cupboard import TheCupboard
from runtime.panda.state_machine import SwarmStateMachine


class TestSwarmScaleAndQuorumStress(unittest.TestCase):
    def setUp(self):
        self.cupboard = TheCupboard(node_timeout_us=1_000_000) # 1.0s timeout
        self.sm = SwarmStateMachine(node_id=1, cupboard=self.cupboard, min_lock_frames=2)

    def test_multi_node_swarm_scaling(self):
        """Simulate a 6-node swarm cluster operating simultaneously."""
        t0 = 10_000_000

        # Add Nodes 10 through 15
        for nid in range(10, 16):
            s = nw.pack_state(nw.MODE_FORMATION_LOCK, nw.LOCK_TRACKING, consensus_ack=True)
            self.cupboard.update_node(
                node_id=nid,
                seq_num=1,
                state_byte=s,
                azimuth_mrad=(nid - 10) * 50 - 125,
                elevation_mrad=20,
                timestamp_us=t0,
            )

        self.assertEqual(self.cupboard.active_node_count, 6)
        self.assertTrue(self.cupboard.is_consensus_reached())
        self.assertEqual(len(self.cupboard.get_proximity_alerts()), 0)

        # Observer Node 1 evaluates ticks
        self.sm.evaluate_tick() # Tick 1: acquiring
        decision = self.sm.evaluate_tick() # Tick 2: tracking & quorum reached -> FORMATION_LOCK

        self.assertEqual(decision.mode, nw.MODE_FORMATION_LOCK)
        self.assertEqual(decision.lock_status, nw.LOCK_HARD_LOCKED)
        self.assertTrue(decision.consensus_ack)

    def test_collision_alert_overrides_unanimous_quorum(self):
        """Even if 5 nodes confirm formation lock, 1 single proximity alert MUST force dispersal."""
        t0 = 10_000_000

        # 5 Nodes in formation lock with consensus ACK
        for nid in range(10, 15):
            s = nw.pack_state(nw.MODE_FORMATION_LOCK, nw.LOCK_HARD_LOCKED, consensus_ack=True)
            self.cupboard.update_node(node_id=nid, seq_num=1, state_byte=s, timestamp_us=t0)

        self.sm.evaluate_tick()
        d_lock = self.sm.evaluate_tick()
        self.assertEqual(d_lock.mode, nw.MODE_FORMATION_LOCK)

        # Node 15 appears and alerts collision danger
        s_prox = nw.pack_state(nw.MODE_DISPERSAL, nw.LOCK_NONE, proximity_alert=True)
        self.cupboard.update_node(node_id=15, seq_num=1, state_byte=s_prox, timestamp_us=t0 + 50_000)

        # State machine MUST override unanimous quorum and command DISPERSAL
        d_abort = self.sm.evaluate_tick()
        self.assertEqual(d_abort.mode, nw.MODE_DISPERSAL)
        self.assertTrue(d_abort.proximity_alert)
        self.assertFalse(d_abort.consensus_ack)

    def test_staggered_cascading_timeout_evictions(self):
        """Verify TTL expiration across nodes with staggered last_seen timestamps."""
        t0 = 1_000_000
        # Node 1 at t0
        s1 = nw.pack_state(nw.MODE_SEARCH, nw.LOCK_NONE)
        self.cupboard.update_node(node_id=101, seq_num=1, state_byte=s1, timestamp_us=t0)

        # Node 2 at t0 + 200ms
        self.cupboard.update_node(node_id=102, seq_num=1, state_byte=s1, timestamp_us=t0 + 200_000)

        # Node 3 at t0 + 500ms
        self.cupboard.update_node(node_id=103, seq_num=1, state_byte=s1, timestamp_us=t0 + 500_000)

        self.assertEqual(self.cupboard.active_node_count, 3)

        # Advance to t0 + 1.1s: Node 101 (age 1.1s > 1.0s) evicted, others kept
        evicted_1 = self.cupboard.evict_stale_nodes(current_time_us=t0 + 1_100_000)
        self.assertEqual(evicted_1, [101])
        self.assertEqual(self.cupboard.active_node_count, 2)

        # Advance to t0 + 1.3s: Node 102 (age 1.1s > 1.0s) evicted, Node 103 (age 0.8s < 1.0s) kept
        evicted_2 = self.cupboard.evict_stale_nodes(current_time_us=t0 + 1_300_000)
        self.assertEqual(evicted_2, [102])
        self.assertEqual(self.cupboard.active_node_count, 1)

        # Advance to t0 + 1.6s: Node 103 evicted, 0 active nodes
        evicted_3 = self.cupboard.evict_stale_nodes(current_time_us=t0 + 1_600_000)
        self.assertEqual(evicted_3, [103])
        self.assertEqual(self.cupboard.active_node_count, 0)


if __name__ == "__main__":
    unittest.main()
