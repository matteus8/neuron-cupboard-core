"""Panda Runtime: Zero-Bloat Optical Front-End Vision Pipeline.

Ingests 850nm bandpass-filtered monochrome frames. Ambient light is cut,
yielding a near-black background with bright modulated optical centroids.
Performs deterministic luminance thresholding, morphological filtering, and
contour centroid / bearing calculation without heavy neural nets.
"""

from typing import List, Tuple, Optional, NamedTuple
import math

# Try importing OpenCV for hardware-accelerated edge execution; provide fallback if absent
try:
    import cv2
    import numpy as np
    HAVE_OPENCV = True
except ImportError:
    HAVE_OPENCV = False


class OpticalCentroid(NamedTuple):
    x: float
    y: float
    intensity: float
    area: float
    azimuth_mrad: int
    elevation_mrad: int


class CameraIntrinsics(NamedTuple):
    fx: float          # Focal length X in pixels
    fy: float          # Focal length Y in pixels
    cx: float          # Principal point X in pixels
    cy: float          # Principal point Y in pixels
    width: int
    height: int


class OpticalTracker:
    """Zero-bloat deterministic blob tracker for 850nm optical payloads."""

    def __init__(
        self,
        intrinsics: CameraIntrinsics,
        luminance_threshold: int = 180,
        min_blob_area: float = 2.0,
        max_blob_area: float = 2500.0,
    ):
        self.intrinsics = intrinsics
        self.threshold = luminance_threshold
        self.min_area = min_blob_area
        self.max_area = max_blob_area

    def process_frame(self, frame_data, width: int = 0, height: int = 0) -> List[OpticalCentroid]:
        """Detect bright 850nm optical blobs and calculate spatial bearings."""
        if HAVE_OPENCV and hasattr(frame_data, "shape"):
            return self._process_opencv(frame_data)
        else:
            return self._process_fallback(frame_data, width or self.intrinsics.width, height or self.intrinsics.height)

    def _process_opencv(self, frame) -> List[OpticalCentroid]:
        """Hardware-accelerated OpenCV luminance and contour centroiding."""
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame

        # 1. Luminance thresholding against near-black filtered background
        _, thresh = cv2.threshold(gray, self.threshold, 255, cv2.THRESH_BINARY)

        # 2. Lightweight morphological opening (3x3 kernel) to eliminate high-frequency shot noise
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        filtered = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

        # 3. Contour extraction and centroid moments
        contours, _ = cv2.findContours(filtered, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        centroids: List[OpticalCentroid] = []

        for cnt in contours:
            m = cv2.moments(cnt)
            area = m["m00"]
            if area < self.min_area or area > self.max_area:
                continue

            cx = m["m10"] / area
            cy = m["m01"] / area

            # Peak intensity at centroid
            px_x, px_y = int(round(cx)), int(round(cy))
            px_x = max(0, min(px_x, gray.shape[1] - 1))
            px_y = max(0, min(px_y, gray.shape[0] - 1))
            intensity = float(gray[px_y, px_x])

            azimuth_mrad, elevation_mrad = self._pixel_to_bearing(cx, cy)
            centroids.append(OpticalCentroid(
                x=cx,
                y=cy,
                intensity=intensity,
                area=area,
                azimuth_mrad=azimuth_mrad,
                elevation_mrad=elevation_mrad,
            ))

        return centroids

    def _process_fallback(self, frame_bytes: bytes, width: int, height: int) -> List[OpticalCentroid]:
        """Pure-Python fallback for bench simulation and host testing."""
        if not isinstance(frame_bytes, (bytes, bytearray)):
            return []

        # Simple connected component / pixel cluster centroid
        total_intensity = 0.0
        sum_x = 0.0
        sum_y = 0.0
        count = 0

        idx = 0
        for y in range(height):
            for x in range(width):
                if idx >= len(frame_bytes):
                    break
                val = frame_bytes[idx]
                if val >= self.threshold:
                    sum_x += x * val
                    sum_y += y * val
                    total_intensity += val
                    count += 1
                idx += 1

        if count < self.min_area or total_intensity == 0:
            return []

        cx = sum_x / total_intensity
        cy = sum_y / total_intensity
        avg_intensity = total_intensity / count

        azimuth_mrad, elevation_mrad = self._pixel_to_bearing(cx, cy)
        return [OpticalCentroid(
            x=cx,
            y=cy,
            intensity=avg_intensity,
            area=float(count),
            azimuth_mrad=azimuth_mrad,
            elevation_mrad=elevation_mrad,
        )]

    def _pixel_to_bearing(self, cx: float, cy: float) -> Tuple[int, int]:
        """Convert pixel coordinate to optical axis bearing in milliradians."""
        dx = cx - self.intrinsics.cx
        dy = cy - self.intrinsics.cy

        azimuth_rad = math.atan2(dx, self.intrinsics.fx)
        elevation_rad = math.atan2(-dy, self.intrinsics.fy)

        azimuth_mrad = int(round(azimuth_rad * 1000.0))
        elevation_mrad = int(round(elevation_rad * 1000.0))
        return azimuth_mrad, elevation_mrad
