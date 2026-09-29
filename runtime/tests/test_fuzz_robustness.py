"""Exhaustive Fuzzing and Ambient Optical Glint Robustness Test Suite.

Stress tests:
1. ManchesterDecoder under randomized chip noise and illegal transition patterns.
2. SpatialPulseTracker under heavy ambient optical glint and false-positive centroids.
3. Wire frame unpacker under random payload mutations and slice truncations.
"""

import unittest
import random
import proto.neuron_wire as nw
from runtime.panda.decoder import ManchesterDecoder
from runtime.panda.multi_tracker import SpatialPulseTracker
from runtime.panda.vision import OpticalCentroid


class TestFuzzAndNoiseRobustness(unittest.TestCase):
    def setUp(self):
        # Seed for reproducible fuzzing
        random.seed(0xDEADBEEF)

    def test_manchester_decoder_fuzzing(self):
        """Feed 5,000 random chips to decoder. Must never crash or emit unverified frames."""
        decoder = ManchesterDecoder(polarity=0)
        random_chips = [random.choice([0, 1]) for _ in range(5000)]

        # Feed chips in varying burst sizes
        idx = 0
        while idx < len(random_chips):
            chunk_size = random.randint(1, 32)
            chunk = random_chips[idx : idx + chunk_size]
            idx += chunk_size

            # Process chunk
            frames = decoder.feed_chips(chunk)
            # Any frame that miraculously survives preamble (0xAA) + sync (0xD5) + CRC-8
            # must strictly be a mathematically valid CRC-8 frame
            for f in frames:
                self.assertEqual(f.preamble, nw.PREAMBLE)
                self.assertEqual(f.sync_word, nw.SYNC_WORD)
                payload = bytes([f.node_id, f.seq_num, f.state_byte])
                self.assertEqual(f.crc8, nw.crc8(payload))

    def test_ambient_optical_glint_resilience(self):
        """Verify that genuine node tracking succeeds despite heavy random optical glints."""
        tracker = SpatialPulseTracker(max_association_distance_px=25.0, max_coast_frames=20)

        # Legitimate Node 42 at stationary position (150.0, 100.0)
        s = nw.pack_state(nw.MODE_FORMATION_LOCK, nw.LOCK_HARD_LOCKED, consensus_ack=True)
        frame_bytes = nw.pack_frame(node_id=42, seq_num=7, state_byte=s)

        # Encode Node 42 to Manchester chips
        node_chips = []
        for b in frame_bytes:
            for bit_pos in range(7, -1, -1):
                bit = (b >> bit_pos) & 1
                node_chips.extend([1, 0] if bit == 0 else [0, 1])

        self.assertEqual(len(node_chips), 96)

        recovered_frames = []

        # Run 96 frame sequence with heavy glint noise injected into each frame
        for chip_idx, chip in enumerate(node_chips):
            centroids = []

            # 1. Genuine emitter signal
            if chip == 1:
                # Add micro-jitter to centroid position (drone vibration simulation: +/- 0.5 px)
                jx = random.uniform(-0.5, 0.5)
                jy = random.uniform(-0.5, 0.5)
                centroids.append(OpticalCentroid(
                    x=150.0 + jx,
                    y=100.0 + jy,
                    intensity=245.0,
                    area=7.0,
                    azimuth_mrad=-100,
                    elevation_mrad=50,
                ))

            # 2. Inject 3 to 8 spurious ambient glints (sun reflection, shiny metal) at random spots
            num_glints = random.randint(3, 8)
            for _ in range(num_glints):
                gx = random.uniform(0.0, 640.0)
                gy = random.uniform(0.0, 480.0)
                # Keep glints outside Node 42 gating radius (>= 40px away)
                if abs(gx - 150.0) > 40.0 or abs(gy - 100.0) > 40.0:
                    centroids.append(OpticalCentroid(
                        x=gx,
                        y=gy,
                        intensity=random.uniform(190.0, 255.0),
                        area=random.uniform(2.0, 15.0),
                        azimuth_mrad=int(gx - 320),
                        elevation_mrad=int(240 - gy),
                    ))

            extracted = tracker.update(centroids)
            for wf, trk in extracted:
                recovered_frames.append(wf)

        # Assert genuine Node 42 frame was recovered despite 96 frames of heavy noise
        node_42_frames = [f for f in recovered_frames if f.node_id == 42]
        self.assertEqual(len(node_42_frames), 1)
        self.assertEqual(node_42_frames[0].seq_num, 7)
        self.assertEqual(node_42_frames[0].state.mode, nw.MODE_FORMATION_LOCK)

        # Coast without glints for 25 frames to verify track pruning
        for _ in range(25):
            tracker.update([])
        # All spurious glint tracks must be pruned
        self.assertEqual(len(tracker.tracks), 0)

    def test_wire_unpacker_fuzzing(self):
        """Feed random corrupt byte payloads to unpack_frame."""
        # 1. Truncated slices (length 0 to 5)
        for length in range(nw.FRAME_LEN):
            truncated = bytes([random.randint(0, 255) for _ in range(length)])
            valid, res = nw.unpack_frame(truncated)
            self.assertFalse(valid)
            self.assertIsNone(res)

        # 2. Random 6-byte mutations
        for _ in range(2000):
            garbage = bytes([random.randint(0, 255) for _ in range(6)])
            valid, res = nw.unpack_frame(garbage)
            if valid:
                # If randomly valid, preamble and sync and CRC MUST match
                self.assertEqual(garbage[0], nw.PREAMBLE)
                self.assertEqual(garbage[1], nw.SYNC_WORD)
                self.assertEqual(garbage[5], nw.crc8(garbage[2:5]))


if __name__ == "__main__":
    unittest.main()
