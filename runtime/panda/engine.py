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
from .multi_tracker import SpatialPulseTracker
from .cupboard import TheCupboard
import proto.neuron_wire as nw


class PandaRuntime:
    """Deterministic edge execution engine for Bamboo Node optical payloads."""

    def __init__(
        self,
        intrinsics: Optional[CameraIntrinsics] = None,
        luminance_threshold: int = 175,
        min_blob_area: float = 8.0,
        max_blob_area: float = 2000.0,
        node_timeout_us: int = 1_000_000,
        on_packet_callback: Optional[Callable[[nw.WireFrame, OpticalCentroid], None]] = None,
        gateway_udp_addr: Optional[Tuple[str, int]] = None,
    ):
        if intrinsics is None:
            # Standard 640x480 monochrome sensor with 6mm lens
            intrinsics = CameraIntrinsics(fx=600.0, fy=600.0, cx=320.0, cy=240.0, width=640, height=480)

        self.intrinsics = intrinsics
        self.tracker = OpticalTracker(
            intrinsics,
            luminance_threshold=luminance_threshold,
            min_blob_area=min_blob_area,
            max_blob_area=max_blob_area,
        )
        self.multi_tracker = SpatialPulseTracker(max_association_distance_px=35.0, max_coast_frames=120, polarity=0)
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

        # 2. Multi-target spatial decoding (SDMA)
        extracted_tuples = self.multi_tracker.update(centroids, timestamp_us)
        extracted_frames: List[nw.WireFrame] = []

        for wire_frame, track in extracted_tuples:
            extracted_frames.append(wire_frame)
            track_centroid = OpticalCentroid(
                x=track.x,
                y=track.y,
                intensity=track.intensity,
                area=1.0,
                azimuth_mrad=track.azimuth_mrad,
                elevation_mrad=track.elevation_mrad,
            )
            self._dispatch_wire_frame(wire_frame, track_centroid, timestamp_us)

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
            except OSError as err:
                sys.stderr.write(f"level=WARN event=udp_forward_failed err={err}\n")

    def run(
        self,
        camera_device: int = 0,
        target_fps: float = 30.0,
        simulate: bool = False,
        max_frames: Optional[int] = None,
    ):
        """Continuous execution loop evaluating optical sensor frames.

        Enforces deterministic, non-blocking timeouts and structured logging.
        Handles SIGINT and SIGTERM gracefully.
        """
        import signal
        from .camera import OpticalCamera

        self.running = True

        def _handle_signal(signum, frame):
            sys.stdout.write(f"level=INFO event=panda_runtime_shutdown_requested sig={signum}\n")
            sys.stdout.flush()
            self.running = False

        # Register signal handlers if running in main thread
        try:
            signal.signal(signal.SIGINT, _handle_signal)
            signal.signal(signal.SIGTERM, _handle_signal)
        except (ValueError, AttributeError):
            pass

        cam = OpticalCamera(
            device_id=camera_device,
            width=self.intrinsics.width,
            height=self.intrinsics.height,
            simulate=simulate,
        )

        frame_interval = 1.0 / max(1.0, target_fps)
        sys.stdout.write(
            f"level=INFO event=panda_runtime_loop_active device={camera_device} "
            f"fps={target_fps} simulate={cam.simulate}\n"
        )
        sys.stdout.flush()

        try:
            while self.running:
                loop_start = time.time()
                frame = cam.grab_frame()

                if frame:
                    self.process_optical_frame(
                        frame.data,
                        timestamp_us=frame.timestamp_us,
                        width=frame.width,
                        height=frame.height,
                    )
                else:
                    time.sleep(0.002)

                if max_frames is not None and self.frames_processed >= max_frames:
                    break

                elapsed = time.time() - loop_start
                sleep_time = frame_interval - elapsed
                if sleep_time > 0.001:
                    time.sleep(sleep_time)
        finally:
            self.running = False
            cam.close()
            if self.udp_sock:
                self.udp_sock.close()
                self.udp_sock = None
            sys.stdout.write(
                f"level=INFO event=panda_runtime_stopped frames_processed={self.frames_processed} "
                f"active_nodes={len(self.cupboard.nodes)}\n"
            )
            sys.stdout.flush()


if __name__ == "__main__":
    import os
    import argparse

    parser = argparse.ArgumentParser(description="Neuron Cupboard: Panda Edge Runtime Engine")
    parser.add_argument("--device", type=int, default=int(os.getenv("NEURON_CAMERA_DEVICE", "0")), help="Camera device index")
    parser.add_argument("--gateway-ip", type=str, default=os.getenv("NEURON_GATEWAY_IP", None), help="Tactical gateway IP for UDP forwarding")
    parser.add_argument("--gateway-port", type=int, default=int(os.getenv("NEURON_GATEWAY_PORT", "9092")), help="Tactical gateway UDP port")
    parser.add_argument("--threshold", type=int, default=int(os.getenv("NEURON_LUMINANCE_THRESHOLD", "175")), help="Luminance threshold (0-255, default 175)")
    parser.add_argument("--min-area", type=float, default=float(os.getenv("NEURON_MIN_BLOB_AREA", "8.0")), help="Minimum blob area in px (default 8.0)")
    parser.add_argument("--max-area", type=float, default=float(os.getenv("NEURON_MAX_BLOB_AREA", "2000.0")), help="Maximum blob area in px (default 2000.0)")
    parser.add_argument("--fps", type=float, default=float(os.getenv("NEURON_TARGET_FPS", "30.0")), help="Target optical evaluation FPS")
    parser.add_argument("--simulate", action="store_true", default=os.getenv("NEURON_SIMULATE", "0") in ("1", "true", "True"), help="Force synthetic optical simulation")
    parser.add_argument("--once", action="store_true", help="Process single self-test frame and exit")
    args = parser.parse_args()

    gw_addr = (args.gateway_ip, args.gateway_port) if args.gateway_ip else None
    print(f"level=INFO event=panda_runtime_init engine=PandaRuntime mode=headless gw={gw_addr} threshold={args.threshold} min_area={args.min_area} max_area={args.max_area}")
    runtime = PandaRuntime(
        gateway_udp_addr=gw_addr,
        luminance_threshold=args.threshold,
        min_blob_area=args.min_area,
        max_blob_area=args.max_area,
    )
    print("level=INFO event=panda_runtime_ready status=listening_optical_front_end")

    max_f = 1 if args.once else None
    runtime.run(camera_device=args.device, target_fps=args.fps, simulate=args.simulate, max_frames=max_f)
