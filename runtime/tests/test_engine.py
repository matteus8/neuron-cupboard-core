"""Unit tests for PandaRuntime continuous engine daemon loop and signal handling."""

import unittest
from runtime.panda.engine import PandaRuntime
from runtime.panda.vision import CameraIntrinsics


class TestPandaRuntimeEngineLoop(unittest.TestCase):
    """Verify PandaRuntime execution loop, synthetic grab, and termination."""

    def test_runtime_engine_bounded_loop(self):
        """Verify that PandaRuntime.run() executes and exits upon max_frames."""
        intrinsics = CameraIntrinsics(fx=400.0, fy=400.0, cx=320.0, cy=240.0, width=640, height=480)
        runtime = PandaRuntime(intrinsics=intrinsics)

        # Run 5 synthetic frames
        runtime.run(camera_device=0, target_fps=100.0, simulate=True, max_frames=5)

        self.assertEqual(runtime.frames_processed, 5)
        self.assertFalse(runtime.running)

    def test_runtime_self_test_flag(self):
        """Verify single self-test frame processing."""
        runtime = PandaRuntime()
        runtime.run(camera_device=0, target_fps=50.0, simulate=True, max_frames=1)
        self.assertEqual(runtime.frames_processed, 1)


if __name__ == "__main__":
    unittest.main()
