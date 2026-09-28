"""Unit tests for Panda Runtime camera ingestion interface."""

import unittest
from runtime.panda.camera import OpticalCamera


class TestOpticalCamera(unittest.TestCase):
    def setUp(self):
        self.cam = OpticalCamera(width=160, height=120, simulate=True)

    def tearDown(self):
        self.cam.close()

    def test_synthetic_dark_frame(self):
        frame = self.cam.grab_frame(active_emitters=None)
        self.assertIsNotNone(frame)
        self.assertEqual(frame.width, 160)
        self.assertEqual(frame.height, 120)
        self.assertEqual(len(frame.data), 160 * 120)
        # Verify background is completely dark (all zeros)
        self.assertEqual(max(frame.data), 0)

    def test_synthetic_emitter_render(self):
        # Render emitter at (80, 60), radius=5, intensity=250
        emitters = [(80, 60, 5, 250, True)]
        frame = self.cam.grab_frame(active_emitters=emitters)
        self.assertIsNotNone(frame)

        # Center pixel must be high intensity
        center_idx = 60 * 160 + 80
        center_val = frame.data[center_idx]
        self.assertGreaterEqual(center_val, 240)


if __name__ == "__main__":
    unittest.main()
