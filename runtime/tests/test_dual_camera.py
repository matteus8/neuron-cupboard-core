"""Unit tests for Dual-Aperture Optical Front-End and Coordinate Transformation.

Verifies dual-camera frame acquisition and fore/aft aperture bearing transforms.
"""

import unittest
from runtime.panda.camera import DualOpticalCamera, OpticalCamera
from runtime.panda.vision import OpticalTracker, OpticalCentroid, CameraIntrinsics


class TestDualOpticalCamera(unittest.TestCase):
    def setUp(self):
        self.intrinsics = CameraIntrinsics(
            fx=400.0,
            fy=400.0,
            cx=320.0,
            cy=240.0,
            width=640,
            height=480,
        )
        self.fore_tracker = OpticalTracker(self.intrinsics, aperture="fore")
        self.aft_tracker = OpticalTracker(self.intrinsics, aperture="aft")
        self.dual_cam = DualOpticalCamera(simulate=True)

    def tearDown(self):
        self.dual_cam.close()

    def test_dual_frame_capture(self):
        """Verify non-blocking acquisition from both fore and aft apertures."""
        fore_emitters = [(320, 240, 5, 250, True)]
        aft_emitters = [(480, 240, 5, 250, True)]

        frame_fore, frame_aft = self.dual_cam.grab_dual_frames(fore_emitters, aft_emitters)

        self.assertIsNotNone(frame_fore)
        self.assertIsNotNone(frame_aft)
        self.assertEqual(frame_fore.width, 640)
        self.assertEqual(frame_aft.width, 640)

        # Process fore frame
        centroids_fore = self.fore_tracker.process_frame(frame_fore.data)
        self.assertEqual(len(centroids_fore), 1)
        self.assertEqual(centroids_fore[0].aperture, "fore")
        # Center of sensor -> 0 mrad fore -> 0 mrad body
        self.assertEqual(centroids_fore[0].azimuth_mrad, 0)
        self.assertEqual(centroids_fore[0].body_azimuth_mrad, 0)

        # Process aft frame
        centroids_aft = self.aft_tracker.process_frame(frame_aft.data)
        self.assertEqual(len(centroids_aft), 1)
        self.assertEqual(centroids_aft[0].aperture, "aft")
        # Center of aft sensor -> 0 mrad aft -> +3141 mrad body (directly behind)
        self.assertAlmostEqual(centroids_aft[0].azimuth_mrad, 381, delta=2) # arctan(160/400)*1000 = 381 mrad
        # Body azimuth = (381 + 3141) mrad normalized
        self.assertNotEqual(centroids_aft[0].body_azimuth_mrad, centroids_aft[0].azimuth_mrad)

    def test_body_frame_azimuth_normalization(self):
        """Verify aft camera aperture rotates azimuth by 180 degrees into body frame."""
        # Blob directly centered on aft boresight
        aft_center = OpticalCentroid(
            x=320.0,
            y=240.0,
            intensity=250.0,
            area=10.0,
            azimuth_mrad=0,
            elevation_mrad=0,
            aperture="aft",
        )
        # Directly behind corresponds to +3141 mrad (180 deg) in body coordinates
        self.assertEqual(abs(aft_center.body_azimuth_mrad), 3141)

        # Blob directly centered on fore boresight
        fore_center = OpticalCentroid(
            x=320.0,
            y=240.0,
            intensity=250.0,
            area=10.0,
            azimuth_mrad=0,
            elevation_mrad=0,
            aperture="fore",
        )
        self.assertEqual(fore_center.body_azimuth_mrad, 0)


if __name__ == "__main__":
    unittest.main()
