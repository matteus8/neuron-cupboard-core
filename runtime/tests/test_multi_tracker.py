"""Unit tests for Panda Runtime spatial multi-target tracker."""

import unittest
import proto.neuron_wire as nw
from runtime.panda.vision import OpticalCentroid
from runtime.panda.multi_tracker import SpatialPulseTracker


class TestSpatialPulseTracker(unittest.TestCase):
    def setUp(self):
        self.tracker = SpatialPulseTracker(max_association_distance_px=30.0, max_coast_frames=50)

    def test_concurrent_dual_node_decoding(self):
        # Prepare Frame for Node 2: Formation lock, consensus ACK
        s2 = nw.pack_state(nw.MODE_FORMATION_LOCK, nw.LOCK_TRACKING, consensus_ack=True)
        f2_bytes = nw.pack_frame(node_id=2, seq_num=10, state_byte=s2)

        # Prepare Frame for Node 3: Search mode, no ACK
        s3 = nw.pack_state(nw.MODE_SEARCH, nw.LOCK_ACQUIRING, consensus_ack=False)
        f3_bytes = nw.pack_frame(node_id=3, seq_num=20, state_byte=s3)

        # Encode both into IEEE 802.3 Manchester chips (96 chips each)
        def to_chips(frame_bytes):
            chips = []
            for b in frame_bytes:
                for bit_pos in range(7, -1, -1):
                    bit = (b >> bit_pos) & 1
                    if bit == 0:
                        chips.extend([1, 0])
                    else:
                        chips.extend([0, 1])
            return chips

        chips2 = to_chips(f2_bytes)
        chips3 = to_chips(f3_bytes)
        self.assertEqual(len(chips2), 96)
        self.assertEqual(len(chips3), 96)

        # Simulate frame-by-frame concurrent optical pulses
        # Node 2 is at (100, 100); Node 3 is at (250, 180)
        recovered_frames = []

        for chip_idx in range(96):
            c2_active = (chips2[chip_idx] == 1)
            c3_active = (chips3[chip_idx] == 1)

            frame_centroids = []
            if c2_active:
                frame_centroids.append(OpticalCentroid(
                    x=100.0, y=100.0, intensity=250.0, area=9.0, azimuth_mrad=-200, elevation_mrad=100
                ))
            if c3_active:
                frame_centroids.append(OpticalCentroid(
                    x=250.0, y=180.0, intensity=245.0, area=8.0, azimuth_mrad=150, elevation_mrad=-50
                ))

            extracted = self.tracker.update(frame_centroids)
            for wf, track in extracted:
                recovered_frames.append(wf)

        # Assert both frames were extracted cleanly!
        self.assertEqual(len(recovered_frames), 2)
        node_ids = sorted([wf.node_id for wf in recovered_frames])
        self.assertEqual(node_ids, [2, 3])

        # Verify decoded states
        f2 = next(wf for wf in recovered_frames if wf.node_id == 2)
        self.assertEqual(f2.seq_num, 10)
        self.assertEqual(f2.state.mode, nw.MODE_FORMATION_LOCK)
        self.assertTrue(f2.state.consensus_ack)

        f3 = next(wf for wf in recovered_frames if wf.node_id == 3)
        self.assertEqual(f3.seq_num, 20)
        self.assertEqual(f3.state.mode, nw.MODE_SEARCH)
        self.assertFalse(f3.state.consensus_ack)

    def test_track_capacity_limiting_dos_protection(self):
        """Verify tracker enforces hard limit on active tracks to prevent memory exhaustion."""
        bounded_tracker = SpatialPulseTracker(max_active_tracks=5, max_coast_frames=10)

        # Flood tracker with 20 distinct centroids in a single frame
        flood_centroids = [
            OpticalCentroid(x=float(i * 30), y=50.0, intensity=240.0, area=5.0, azimuth_mrad=0, elevation_mrad=0)
            for i in range(20)
        ]

        bounded_tracker.update(flood_centroids)
        # Must be strictly capped at 5 tracks
        self.assertLessEqual(len(bounded_tracker.tracks), 5)


if __name__ == "__main__":
    unittest.main()

