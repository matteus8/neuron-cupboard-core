#!/usr/bin/env python3
"""Neuron Cupboard: Physical Hardware Bench Diagnostic & Alignment Tool.

Provides real-time terminal utilities for physical optical bench bringup:
1. --mode=scan         : Discover connected RP2040 Pico serial ports and camera devices.
2. --mode=camera-align : ASCII terminal visualizer for lens focusing and 850nm optical filter tuning.
3. --mode=rx-decode    : Live optical pulse decoder with real-time bearing extraction and CRC-8 check.
4. --mode=tx-sim       : Hardware transmitter loopback test emitting 850nm Manchester chips.
"""

import sys
import os
import time
import glob
import argparse
from typing import Optional, List

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from runtime.panda.camera import OpticalCamera, CameraFrame
from runtime.panda.vision import OpticalTracker, CameraIntrinsics, OpticalCentroid
from runtime.panda.multi_tracker import SpatialPulseTracker
import proto.neuron_wire as nw


def scan_devices():
    """Scan and print connected microcontroller serial ports and video devices."""
    print("=" * 60)
    print("   NEURON CUPBOARD: HARDWARE DEVICE DISCOVERY")
    print("=" * 60)

    # 1. Serial devices (RP2040 Pico)
    serial_patterns = [
        "/dev/tty.usbmodem*",    # macOS USB CDC
        "/dev/ttyACM*",          # Linux USB CDC
        "/dev/ttyAMA0",          # Raspberry Pi 5 Hardware UART
        "/dev/serial0",          # Raspberry Pi Serial alias
    ]
    found_serial = []
    for pat in serial_patterns:
        found_serial.extend(glob.glob(pat))

    print("\n[+] Microcontroller Serial Interfaces (RP2040 / Pico):")
    if found_serial:
        for dev in found_serial:
            print(f"  -> {dev} [READY]")
    else:
        print("  [!] No hardware serial ports detected (Connect Pico via USB/UART).")

    # 2. Video Capture devices (Monochrome Global Shutter Cameras)
    video_devices = glob.glob("/dev/video*")
    print("\n[+] Video Ingestion Apertures (V4L2 Cameras):")
    if video_devices:
        for vdev in sorted(video_devices):
            print(f"  -> {vdev} [DETECTED]")
    else:
        print("  [!] No /dev/video* devices found (Using synthetic optical simulation).")

    print("\n" + "=" * 60)


def render_ascii_frame(frame: CameraFrame, centroids: List[OpticalCentroid], grid_w: int = 40, grid_h: int = 15):
    """Render a live 2D ASCII grid representation of the optical front-end."""
    data = frame.data
    fw, fh = frame.width, frame.height
    step_x = fw // grid_w
    step_y = fh // grid_h

    # Build ASCII grid
    lines = []
    lines.append("+" + "-" * grid_w + "+")
    for gy in range(grid_h):
        row_chars = []
        py = min(fh - 1, gy * step_y)
        for gx in range(grid_w):
            px = min(fw - 1, gx * step_x)
            val = data[py * fw + px]

            # Check if near any detected centroid
            is_centroid = False
            for c in centroids:
                if abs(c.x - px) < step_x * 1.5 and abs(c.y - py) < step_y * 1.5:
                    is_centroid = True
                    break

            if is_centroid:
                row_chars.append("*")  # Centroid marker
            elif val > 200:
                row_chars.append("#")  # High intensity saturation
            elif val > 140:
                row_chars.append("+")  # Moderate intensity
            elif val > 80:
                row_chars.append(":")  # Low intensity
            elif val > 30:
                row_chars.append(".")  # Ambient leakage
            else:
                row_chars.append(" ")  # Near-black filtered background
        lines.append("|" + "".join(row_chars) + "|")
    lines.append("+" + "-" * grid_w + "+")
    return "\n".join(lines)


def run_camera_align(device_id: int, iterations: int = 50, synthetic: bool = False, min_area: float = 15.0, max_area: float = 25000.0, threshold: int = 160):
    """Interactive optical alignment tool for lens focusing and 850nm filter testing."""
    print("=" * 60)
    print("   850nm OPTICAL FRONT-END ALIGNMENT & LENS FOCUS TOOL")
    print("   Aim 850nm emitter at lens. Adjust focus until [*] appears.")
    print(f"   Config: threshold={threshold}, min_blob_area={min_area:.0f}px, max_blob_area={max_area:.0f}px")
    print("=" * 60)

    cam = OpticalCamera(device_id=device_id, width=640, height=480, simulate=synthetic)
    intrinsics = CameraIntrinsics(fx=450.0, fy=450.0, cx=320.0, cy=240.0, width=640, height=480)
    tracker = OpticalTracker(intrinsics, luminance_threshold=threshold, min_blob_area=min_area, max_blob_area=max_area)

    total_frames = iterations if iterations > 0 else 1_000_000
    frame_count = 0

    try:
        while frame_count < total_frames:
            frame_count += 1
            # In synthetic mode, simulate an emitter at center
            emitters = [(320, 240, 6, 245, True)] if cam.simulate else None
            frame = cam.grab_frame(emitters)
            if not frame:
                time.sleep(0.05)
                continue

            centroids = tracker.process_frame(frame.data)
            ascii_grid = render_ascii_frame(frame, centroids)

            # Clear screen and render
            iter_label = f"Frame {frame_count}/{iterations}" if iterations > 0 else f"Frame {frame_count} (Press Ctrl+C to exit)"
            sys.stdout.write("\033[H\033[J")
            sys.stdout.write(f"NEURON CUPBOARD: OPTICAL ALIGNMENT ({iter_label})\n")
            sys.stdout.write(ascii_grid + "\n")

            if centroids:
                for idx, c in enumerate(centroids):
                    sys.stdout.write(
                        f"  -> BLOB #{idx+1}: Intensity={c.intensity:.0f}/255 | "
                        f"Area={c.area:.1f}px | Azimuth={c.azimuth_mrad:+d} mrad | "
                        f"Elevation={c.elevation_mrad:+d} mrad\n"
                    )
            else:
                sys.stdout.write("  [!] Optical front-end DARK. No 850nm emitters detected above threshold.\n")

            sys.stdout.flush()
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        cam.close()
    print("\nAlignment session closed.")


def run_rx_decoder(device_id: int, duration_sec: int = 10, synthetic: bool = False, min_area: float = 15.0, max_area: float = 25000.0, threshold: int = 160):
    """Live optical pulse train decoder with spatial division tracking."""
    print("=" * 60)
    print("   LIVE OPTICAL RECEIVER & SPATIAL PULSE DECODER")
    print("   Listening for 850nm Manchester modulated beacons...")
    print(f"   Config: threshold={threshold}, min_blob_area={min_area:.0f}px, max_blob_area={max_area:.0f}px")
    print("=" * 60)

    cam = OpticalCamera(device_id=device_id, width=640, height=480, simulate=synthetic)
    intrinsics = CameraIntrinsics(fx=450.0, fy=450.0, cx=320.0, cy=240.0, width=640, height=480)
    tracker = OpticalTracker(intrinsics, luminance_threshold=threshold, min_blob_area=min_area, max_blob_area=max_area)
    pulse_tracker = SpatialPulseTracker(max_association_distance_px=30.0)

    # For synthetic demonstration, prepare a 96-chip frame from Node 7
    node_id = 7
    seq = 42
    st = nw.pack_state(nw.MODE_FORMATION_LOCK, nw.LOCK_HARD_LOCKED, True, False, False, False)
    wire = nw.pack_frame(node_id, seq, st)
    chips = nw.encode_manchester(wire)
    chip_idx = 0

    start_time = time.time()
    end_time = start_time + duration_sec
    recovered_count = 0
    total_frames_captured = 0

    try:
        while time.time() < end_time:
            if cam.simulate:
                cur_chip = chips[chip_idx % len(chips)]
                chip_idx += 1
                emitters = [(320.0, 240.0, 5.0, 245.0, cur_chip == 1)]
            else:
                emitters = None

            frame = cam.grab_frame(emitters)
            if not frame:
                time.sleep(0.005)
                continue

            total_frames_captured += 1
            centroids = tracker.process_frame(frame.data)
            completed_frames = pulse_tracker.update(centroids)

            # Live diagnostic feedback on every frame
            if not cam.simulate:
                elapsed = time.time() - start_time
                current_fps = total_frames_captured / max(elapsed, 0.001)

                if centroids:
                    # Select largest centroid (primary emitter) for HUD readout
                    c = max(centroids, key=lambda b: b.area)
                    blob_str = f"BLOB #{len(centroids)} | I={c.intensity:.0f}/255 A={c.area:.0f}px"
                    pulse = "●"
                else:
                    blob_str = "DARK (0/255)                "
                    pulse = "○"

                total_bits = sum(len(t.decoder.bit_stream) for t in pulse_tracker.tracks.values())
                primary_t = max(pulse_tracker.tracks.values(), key=lambda t: len(t.decoder.bit_stream), default=None) if pulse_tracker.tracks else None
                hex_prev = ""
                if primary_t and len(primary_t.decoder.bit_stream) >= 8:
                    hex_prev = f" | Hex: {primary_t.decoder.get_bitstream_hex()[-17:]}"

                sys.stdout.write(f"\r[{time.strftime('%H:%M:%S')}] Pulse: {pulse} | {blob_str} | {current_fps:.1f} FPS | Tracks: {len(pulse_tracker.tracks)} | Bits: {total_bits}{hex_prev} | Frames: {recovered_count}")
                sys.stdout.flush()

            for wire_frame, track in completed_frames:
                recovered_count += 1
                mode, lock, ack, prox, swap, sync = nw.unpack_state(wire_frame.state_byte)
                print(
                    f"\n[{time.strftime('%H:%M:%S')}] >>> RECOVERED FRAME #{recovered_count} | "
                    f"Node={wire_frame.node_id} | Seq={wire_frame.seq_num} | "
                    f"Mode={mode} | Lock={lock} | ACK={ack} | Prox={prox} | "
                    f"Bearing={track.azimuth_mrad:+d} mrad | CRC=0x{wire_frame.crc8:02X} [VALID]"
                )

            if not cam.simulate:
                time.sleep(0.001)
    finally:
        cam.close()

    print(f"\nDecoding session complete. Total verified frames recovered: {recovered_count}")
    if not cam.simulate and total_frames_captured > 0:
        elapsed = time.time() - start_time
        print(f"Captured {total_frames_captured} frames in {elapsed:.1f}s ({total_frames_captured / max(elapsed, 0.001):.1f} FPS)")
        if pulse_tracker.tracks:
            print("\n--- Optical Track Diagnostic Report ---")
            for t_id, track in sorted(pulse_tracker.tracks.items()):
                info = track.decoder.inspect_stream()
                print(f"  Track #{t_id} at ({track.x:.1f}, {track.y:.1f}) [Az: {track.azimuth_mrad:+d} mrad, El: {track.elevation_mrad:+d} mrad]:")
                print(f"    Bits: {info['bit_count']} | Hex: {info['hex'] or '(none)'}")
                print(f"    Preamble (0xAA): {'FOUND' if info['preamble_found'] else 'MISSING'} | Sync (0xD5): {'FOUND' if info['sync_found'] else 'MISSING'}")
                if info['crc_err']:
                    print(f"    CRC Check: FAILED ({info['crc_err']})")


def main():
    parser = argparse.ArgumentParser(description="Neuron Cupboard Hardware Bench Diagnostic Tool")
    parser.add_argument(
        "--mode",
        choices=["scan", "camera-align", "rx-decode"],
        default="scan",
        help="Diagnostic mode to execute",
    )
    parser.add_argument("--device", type=int, default=0, help="Camera device index (/dev/videoN)")
    parser.add_argument("--duration", type=int, default=10, help="Execution duration in seconds")
    parser.add_argument("--threshold", type=int, default=160, help="Luminance threshold (0-255, default 160)")
    parser.add_argument("--min-area", type=float, default=15.0, help="Minimum blob area in px (default 15.0)")
    parser.add_argument("--max-area", type=float, default=25000.0, help="Maximum blob area in px (default 25000.0)")
    parser.add_argument("--iterations", type=int, default=50, help="Frames for camera-align (0 for continuous, default 50)")
    parser.add_argument("--synthetic", action="store_true", help="Force synthetic optical simulation")
    args = parser.parse_args()

    if args.mode == "scan":
        scan_devices()
    elif args.mode == "camera-align":
        run_camera_align(
            device_id=args.device,
            iterations=args.iterations,
            synthetic=args.synthetic,
            min_area=args.min_area,
            max_area=args.max_area,
            threshold=args.threshold,
        )
    elif args.mode == "rx-decode":
        run_rx_decoder(
            device_id=args.device,
            duration_sec=args.duration,
            synthetic=args.synthetic,
            min_area=args.min_area,
            max_area=args.max_area,
            threshold=args.threshold,
        )


if __name__ == "__main__":
    main()
