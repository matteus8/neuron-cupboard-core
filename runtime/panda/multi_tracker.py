"""Panda Runtime: Spatial Multi-Target Optical Pulse Tracker (SDMA).

Enables concurrent reception of multiple optical pulse trains from distinct
Bamboo Nodes in the camera's field of view. Gating and spatial association
prevent cross-talk, routing each optical centroid to an independent ManchesterDecoder.
"""

from typing import Dict, List, Optional, Tuple, NamedTuple
import math
import time

from .vision import OpticalCentroid
from .decoder import ManchesterDecoder
import proto.neuron_wire as nw


class OpticalTrack:
    """Represents a spatially tracked 850nm optical emitter channel."""

    def __init__(
        self,
        track_id: int,
        x: float,
        y: float,
        azimuth_mrad: int,
        elevation_mrad: int,
        intensity: float,
        timestamp_us: int,
        polarity: int = 0,
    ):
        self.track_id = track_id
        self.x = x
        self.y = y
        self.azimuth_mrad = azimuth_mrad
        self.elevation_mrad = elevation_mrad
        self.intensity = intensity
        self.last_seen_us = timestamp_us
        self.frames_since_match = 0
        self.decoder = ManchesterDecoder(polarity=polarity)
        self.bound_node_id: Optional[int] = None

    def distance_to(self, cx: float, cy: float) -> float:
        dx = self.x - cx
        dy = self.y - cy
        return math.hypot(dx, dy)


class SpatialPulseTracker:
    """Associates 850nm blobs across frames and decodes concurrent pulse streams."""

    def __init__(
        self,
        max_association_distance_px: float = 30.0,
        max_coast_frames: int = 150,
        polarity: int = 0,
    ):
        self.max_distance = max_association_distance_px
        self.max_coast_frames = max_coast_frames
        self.polarity = polarity
        self.tracks: Dict[int, OpticalTrack] = {}
        self.next_track_id = 1

    def update(
        self,
        centroids: List[OpticalCentroid],
        timestamp_us: Optional[int] = None,
    ) -> List[Tuple[nw.WireFrame, OpticalTrack]]:
        """Process incoming frame centroids, feed track decoders, and extract wire frames."""
        if timestamp_us is None:
            timestamp_us = int(time.time() * 1_000_000)

        # 1. Spatial Association (Greedy nearest neighbor within max_distance)
        unmatched_centroids = list(centroids)
        matched_tracks = set()

        for track_id, track in list(self.tracks.items()):
            best_idx = None
            best_dist = float("inf")

            for idx, c in enumerate(unmatched_centroids):
                dist = track.distance_to(c.x, c.y)
                if dist < best_dist and dist <= self.max_distance:
                    best_dist = dist
                    best_idx = idx

            if best_idx is not None:
                # Match found: update track position and feed chip 1
                matched_c = unmatched_centroids.pop(best_idx)
                # Alpha filter position update
                track.x = 0.8 * track.x + 0.2 * matched_c.x
                track.y = 0.8 * track.y + 0.2 * matched_c.y
                track.azimuth_mrad = matched_c.azimuth_mrad
                track.elevation_mrad = matched_c.elevation_mrad
                track.intensity = matched_c.intensity
                track.last_seen_us = timestamp_us
                track.frames_since_match = 0
                track.decoder.feed_chip(1)
                matched_tracks.add(track_id)
            else:
                # No centroid nearby: emitter is in LOW half-bit phase or idle
                track.frames_since_match += 1
                track.decoder.feed_chip(0)

        # 2. Spawn new tracks for remaining unmatched centroids
        for c in unmatched_centroids:
            new_track = OpticalTrack(
                track_id=self.next_track_id,
                x=c.x,
                y=c.y,
                azimuth_mrad=c.azimuth_mrad,
                elevation_mrad=c.elevation_mrad,
                intensity=c.intensity,
                timestamp_us=timestamp_us,
                polarity=self.polarity,
            )
            self.next_track_id += 1
            # Prior optical quiescent state of bandpass front-end is dark (0)
            new_track.decoder.feed_chip(0)
            new_track.decoder.feed_chip(1)
            self.tracks[new_track.track_id] = new_track

        # 3. Check for decoded frames across all active tracks
        extracted_frames: List[Tuple[nw.WireFrame, OpticalTrack]] = []
        for track in list(self.tracks.values()):
            wire_frame = track.decoder._try_extract_frame()
            if wire_frame:
                track.bound_node_id = wire_frame.node_id
                extracted_frames.append((wire_frame, track))

        # 4. Prune stale tracks that have exceeded coast threshold
        for track_id, track in list(self.tracks.items()):
            if track.frames_since_match > self.max_coast_frames:
                del self.tracks[track_id]

        return extracted_frames
