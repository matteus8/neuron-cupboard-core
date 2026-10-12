"""Panda Runtime: Zero-Bloat Optical Front-End Vision Pipeline.

Ingests 850nm bandpass-filtered monochrome frames. Ambient light is cut,
yielding a near-black background with bright modulated optical centroids.
Performs deterministic luminance thresholding, morphological filtering, and
contour centroid / bearing calculation without heavy neural nets.
"""

from typing import List, Tuple, Optional, NamedTuple
from collections import deque
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
    aperture: str = "fore"

    @property
    def body_azimuth_mrad(self) -> int:
        """Transform aperture-relative azimuth into drone body coordinate frame [-3141, +3141] mrad."""
        if self.aperture == "aft":
            val = self.azimuth_mrad + 3141
            return ((val + 3141) % 6283) - 3141
        return self.azimuth_mrad


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
        luminance_threshold: int = 160,
        min_blob_area: float = 15.0,
        max_blob_area: float = 25000.0,
        aperture: str = "fore",
    ):
        self.intrinsics = intrinsics
        self.threshold = luminance_threshold
        self.min_area = min_blob_area
        self.max_area = max_blob_area
        self.aperture = aperture

    def process_frame(self, frame_data, width: int = 0, height: int = 0) -> List[OpticalCentroid]:
        """Detect bright 850nm optical blobs and calculate spatial bearings."""
        if HAVE_OPENCV:
            if hasattr(frame_data, "shape"):
                return self._process_opencv(frame_data)
            elif isinstance(frame_data, (bytes, bytearray)):
                w = width or self.intrinsics.width
                h = height or self.intrinsics.height
                if len(frame_data) >= w * h:
                    arr = np.frombuffer(frame_data[:w * h], dtype=np.uint8).reshape((h, w))
                    return self._process_opencv(arr)
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
                aperture=self.aperture,
            ))

        return centroids

    def _process_fallback(self, frame_bytes: bytes, width: int, height: int) -> List[OpticalCentroid]:
        """Pure-Python spatial clustering for multi-target optical blobs."""
        if not isinstance(frame_bytes, (bytes, bytearray)):
            return []

        bright_pixels = []
        idx = 0
        for y in range(height):
            for x in range(width):
                if idx >= len(frame_bytes):
                    break
                val = frame_bytes[idx]
                if val >= self.threshold:
                    bright_pixels.append((x, y, val))
                idx += 1

        if not bright_pixels:
            return []

        # Cluster bright pixels by connected components (8-connectivity)
        pixel_map = {(x, y): val for x, y, val in bright_pixels}
        visited = set()
        clusters: List[List[Tuple[int, int, int]]] = []

        for p in bright_pixels:
            pt = (p[0], p[1])
            if pt in visited:
                continue

            cluster = []
            queue = deque([pt])
            visited.add(pt)

            while queue:
                curr_x, curr_y = queue.popleft()
                cluster.append((curr_x, curr_y, pixel_map[(curr_x, curr_y)]))

                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        neighbor = (curr_x + dx, curr_y + dy)
                        if neighbor in pixel_map and neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)

            clusters.append(cluster)

        centroids: List[OpticalCentroid] = []
        for cluster in clusters:
            if len(cluster) < self.min_area or len(cluster) > self.max_area:
                continue

            sum_x = 0.0
            sum_y = 0.0
            total_intensity = 0.0
            max_intensity = 0

            for px, py, pval in cluster:
                sum_x += px * pval
                sum_y += py * pval
                total_intensity += pval
                if pval > max_intensity:
                    max_intensity = pval

            if total_intensity == 0:
                continue

            cx = sum_x / total_intensity
            cy = sum_y / total_intensity

            azimuth_mrad, elevation_mrad = self._pixel_to_bearing(cx, cy)
            centroids.append(OpticalCentroid(
                x=cx,
                y=cy,
                intensity=float(max_intensity),
                area=float(len(cluster)),
                azimuth_mrad=azimuth_mrad,
                elevation_mrad=elevation_mrad,
                aperture=self.aperture,
            ))

        return centroids

    def _pixel_to_bearing(self, cx: float, cy: float) -> Tuple[int, int]:
        """Convert pixel coordinate to optical axis bearing in milliradians."""
        dx = cx - self.intrinsics.cx
        dy = cy - self.intrinsics.cy

        azimuth_rad = math.atan2(dx, self.intrinsics.fx)
        elevation_rad = math.atan2(-dy, self.intrinsics.fy)

        azimuth_mrad = int(round(azimuth_rad * 1000.0))
        elevation_mrad = int(round(elevation_rad * 1000.0))
        return azimuth_mrad, elevation_mrad
