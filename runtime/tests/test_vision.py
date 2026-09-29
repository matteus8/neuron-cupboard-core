"""Unit tests for Panda Runtime vision tracking and bearing calculations."""

import unittest
from runtime.panda.vision import OpticalTracker, CameraIntrinsics


class TestOpticalTracker(unittest.TestCase):
    def setUp(self):
        # 100x100 virtual sensor, fx=100, fy=100, cx=50, cy=50
        self.intrinsics = CameraIntrinsics(fx=100.0, fy=100.0, cx=50.0, cy=50.0, width=100, height=100)
        self.tracker = OpticalTracker(self.intrinsics, luminance_threshold=200, min_blob_area=1.0)

    def test_centroid_at_boresight(self):
        # Create 100x100 image with 3x3 bright spot centered at (50, 50)
        img = bytearray(100 * 100)
        for y in range(49, 52):
            for x in range(49, 52):
                img[y * 100 + x] = 255

        centroids = self.tracker.process_frame(bytes(img), width=100, height=100)
        self.assertEqual(len(centroids), 1)

        c = centroids[0]
        self.assertAlmostEqual(c.x, 50.0, places=1)
        self.assertAlmostEqual(c.y, 50.0, places=1)
        # Boresight bearing should be 0 mrad
        self.assertEqual(c.azimuth_mrad, 0)
        self.assertEqual(c.elevation_mrad, 0)

    def test_offset_bearing_calculation(self):
        # Place bright spot at (60, 40) -> dx=+10, dy=-10
        # dx=10, fx=100 -> atan(0.10) ~ 99.6 mrad -> 100 mrad
        # dy=-10 (up in image), elevation should be positive
        img = bytearray(100 * 100)
        for y in range(39, 42):
            for x in range(59, 62):
                img[y * 100 + x] = 255

        centroids = self.tracker.process_frame(bytes(img), width=100, height=100)
        self.assertEqual(len(centroids), 1)

        c = centroids[0]
        self.assertAlmostEqual(c.x, 60.0, places=1)
        self.assertAlmostEqual(c.y, 40.0, places=1)
        self.assertGreater(c.azimuth_mrad, 90)
        self.assertLess(c.azimuth_mrad, 110)
        self.assertGreater(c.elevation_mrad, 90)
        self.assertLess(c.elevation_mrad, 110)

    def test_dark_frame_no_blobs(self):
        # Empty background frame (near-black)
        img = bytes(100 * 100)
        centroids = self.tracker.process_frame(img, width=100, height=100)
        self.assertEqual(len(centroids), 0)

    def test_multiple_simultaneous_blobs(self):
        # Spot 1 at (25, 25), Spot 2 at (75, 75)
        img = bytearray(100 * 100)
        for y in range(24, 27):
            for x in range(24, 27):
                img[y * 100 + x] = 255
        for y in range(74, 77):
            for x in range(74, 77):
                img[y * 100 + x] = 255

        centroids = self.tracker.process_frame(bytes(img), width=100, height=100)
        self.assertEqual(len(centroids), 2)
        xs = sorted([c.x for c in centroids])
        self.assertAlmostEqual(xs[0], 25.0, places=1)
        self.assertAlmostEqual(xs[1], 75.0, places=1)


if __name__ == "__main__":
    unittest.main()
