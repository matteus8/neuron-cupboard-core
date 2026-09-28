"""Panda Runtime: Edge Execution Engine.

Evaluates incoming 850nm optical sensor frames, tracks emitter centroids,
decodes Manchester pulse trains, and maintains swarm state transitions.
Operates strictly headless with structured key-value logs and deterministic timeouts.
"""

import time
import sys
from typing import Optional, List, Callable, Tuple

from .vision import OpticalTracker, CameraIntrinsics, OpticalCentroid
from .decoder import ManchesterDecoder
from .cupboard import TheCupboard
import proto.neuron_wire as nw


class PandaRuntime:
    """Deterministic edge execution engine for Bamboo Node optical payloads."""

    def __init__(
        self,
        intrinsics: Optional[CameraIntrinsics] = None,
        luminance_threshold: int = 180,
        node_timeout_us: int = 1_000_000,
        on_packet_callback: Optional[Callable[[nw.WireFrame, OpticalCentroid], None]] = None,
        gateway_udp_addr: Optional[Tuple[str, int]] = None,
    ):
        if intrinsics is None:
            # Standard 640x480 monochrome sensor with 6mm lens
            intrinsics = CameraIntrinsics(fx=600.0, fy=600.0, cx=320.0, cy=240.0, width=640, height=480)

        self.intrinsics = intrinsics
        self.tracker = OpticalTracker(intrinsics, luminance_threshold=luminance_threshold)
        self.decoder = ManchesterDecoder(polarity=0) # IEEE 802.3
        self.cupboard = TheCupboard(node_timeout_us=node_timeout_us)
        self.on_packet_callback = on_packet_callback
        self.gateway_udp_addr = gateway_udp_addr
        self.running = False
        self.frames_processed = 0

        self.udp_sock = None
        if self.gateway_udp_addr:
            import socket
            self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_sock.setblocking(False)

        self.last_centroid: Optional[OpticalCentroid] = None

    def process_optical_frame(
        self,
        frame_data,
        timestamp_us: Optional[int] = None,
        width: int = 0,
        height: int = 0,
    ) -> List[nw.WireFrame]:
        """Process a single monochrome frame with bounded execution time."""
        if timestamp_us is None:
            timestamp_us = int(time.time() * 1_000_000)

        self.frames_processed += 1

        # 1. Zero-bloat blob tracking
        centroids = self.tracker.process_frame(frame_data, width, height)

        # 2. Decode pulse trains
        extracted_frames: List[nw.WireFrame] = []
        if centroids:
            # Modulated signal detected: high luminance = chip 1
            primary_blob = centroids[0]
            self.last_centroid = primary_blob
            chip_val = 1 if primary_blob.intensity > self.tracker.threshold else 0
            self.decoder.feed_chip(chip_val)
        else:
            # Background / low intensity = chip 0
            self.decoder.feed_chip(0)

        wire_frame = self.decoder._try_extract_frame()
        if wire_frame:
            extracted_frames.append(wire_frame)
            self._dispatch_wire_frame(wire_frame, self.last_centroid, timestamp_us)

        # 3. Deterministic stale node eviction
        self.cupboard.evict_stale_nodes(timestamp_us)
        return extracted_frames

    def _dispatch_wire_frame(
        self,
        wire_frame: nw.WireFrame,
        centroid: Optional[OpticalCentroid],
        timestamp_us: int,
    ):
        az_mrad = centroid.azimuth_mrad if centroid else 0
        el_mrad = centroid.elevation_mrad if centroid else 0

        self.cupboard.update_node(
            node_id=wire_frame.node_id,
            seq_num=wire_frame.seq_num,
            state_byte=wire_frame.state_byte,
            azimuth_mrad=az_mrad,
            elevation_mrad=el_mrad,
            timestamp_us=timestamp_us,
        )
        if self.on_packet_callback:
            self.on_packet_callback(wire_frame, centroid)
        if self.udp_sock and self.gateway_udp_addr:
            try:
                raw_wire = nw.pack_frame(wire_frame.node_id, wire_frame.seq_num, wire_frame.state_byte)
                self.udp_sock.sendto(raw_wire, self.gateway_udp_addr)
            except Exception:
                pass


if __name__ == "__main__":
    print("level=INFO event=panda_runtime_init engine=PandaRuntime mode=headless")
    runtime = PandaRuntime()
    print("level=INFO event=panda_runtime_ready status=listening_optical_front_end")
