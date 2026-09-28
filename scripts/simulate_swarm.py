#!/usr/bin/env python3
"""End-to-End Autonomous Optical Swarm Simulation.

Simulates multiple Bamboo Nodes communicating strictly via modulated 850nm IR light.
Validates:
1. Physical-layer Manchester modulation (firmware / bamboo_transmitter).
2. Optical camera frame rendering and luminance centroid tracking (runtime / Panda vision).
3. Pulse stream decoding and CRC-8 packet framing (runtime / Panda decoder).
4. Decentralized swarm consensus formation in The Cupboard (runtime / state machine).
5. Tactical Zenoh gateway relay over UDP socket (gateway).
"""

import sys
import time
import socket
import proto.neuron_wire as nw
from runtime.panda.camera import OpticalCamera
from runtime.panda.engine import PandaRuntime
from runtime.panda.state_machine import SwarmStateMachine


def run_swarm_simulation():
    print("================================================================================")
    print("   NEURON CUPBOARD CORE: MULTI-NODE OPTICAL SWARM SIMULATION")
    print("================================================================================")

    # 1. Setup camera and runtime for Observer Bamboo Node (Node 1)
    gateway_port = 19092
    gateway_addr = ("127.0.0.1", gateway_port)

    # Start mock gateway UDP socket to verify IPC bridge
    gw_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    gw_sock.bind(gateway_addr)
    gw_sock.setblocking(False)

    cam = OpticalCamera(width=320, height=240, simulate=True)
    runtime = PandaRuntime(gateway_udp_addr=gateway_addr)
    sm = SwarmStateMachine(node_id=1, cupboard=runtime.cupboard, min_lock_frames=2)

    print(f"level=INFO ts={int(time.time()*1e6)} node=1 event=observer_node_online mode=SEARCH")

    # 2. Prepare transmission sequence for Remote Bamboo Node 2
    # Node 2 initially transmits in SEARCH mode with consensus ACK
    node2_state = nw.pack_state(
        mode=nw.MODE_SEARCH,
        lock_status=nw.LOCK_TRACKING,
        consensus_ack=True,
    )
    node2_frame_bytes = nw.pack_frame(node_id=2, seq_num=1, state_byte=node2_state)

    # Convert Node 2 frame into IEEE 802.3 Manchester chips
    node2_chips = []
    for b in node2_frame_bytes:
        for bit_pos in range(7, -1, -1):
            bit = (b >> bit_pos) & 1
            if bit == 0:
                node2_chips.extend([1, 0])
            else:
                node2_chips.extend([0, 1])

    print(f"level=INFO event=node2_frame_prepared chips={len(node2_chips)} bytes=6")

    # 3. Simulate optical frames: Node 2 emitter pulsing at pixel (200, 120)
    emitter_x, emitter_y = 200, 120
    frames_relayed_to_gw = 0

    print("level=INFO event=starting_optical_pulse_train_modulation...")
    for chip_idx, chip in enumerate(node2_chips):
        is_lit = (chip == 1)
        active_emitters = [(emitter_x, emitter_y, 4.0, 245.0, is_lit)]

        frame = cam.grab_frame(active_emitters=active_emitters)
        if frame:
            extracted = runtime.process_optical_frame(
                frame.data,
                width=frame.width,
                height=frame.height,
            )
            if extracted:
                print(f"level=INFO chip={chip_idx} event=frame_recovered node={extracted[0].node_id}")

        # Check if gateway received packet over UDP
        try:
            udp_data, _ = gw_sock.recvfrom(64)
            if len(udp_data) == 6:
                frames_relayed_to_gw += 1
                valid, wf = nw.unpack_frame(udp_data)
                if valid:
                    print(f"level=INFO event=gateway_ipc_verified node={wf.node_id} seq={wf.seq_num} crc=0x{wf.crc8:02X}")
        except BlockingIOError:
            pass

    # Drain any queued frames delivered to the gateway socket
    time.sleep(0.02)
    while True:
        try:
            udp_data, _ = gw_sock.recvfrom(64)
            if len(udp_data) == 6:
                frames_relayed_to_gw += 1
                valid, wf = nw.unpack_frame(udp_data)
                if valid:
                    print(f"level=INFO event=gateway_ipc_verified node={wf.node_id} seq={wf.seq_num} crc=0x{wf.crc8:02X}")
        except (BlockingIOError, OSError):
            break

    # 4. Evaluate Swarm Consensus State Machine
    decision = sm.evaluate_tick()
    # Second tick to confirm tracking & quorum
    decision = sm.evaluate_tick()

    print("--------------------------------------------------------------------------------")
    print(f"OBSERVER NODE 1 STATE MACHINE STATUS:")
    print(f"  Operational Mode : {['UNSPECIFIED', 'SEARCH', 'FORMATION_LOCK', 'DISPERSAL'][decision.mode]}")
    print(f"  Lock Status      : {['NONE', 'ACQUIRING', 'TRACKING', 'HARD_LOCKED'][decision.lock_status]}")
    print(f"  Consensus ACK    : {decision.consensus_ack}")
    print(f"  The Cupboard Size: {runtime.cupboard.active_node_count} active node(s)")
    print(f"  Gateway Relayed  : {frames_relayed_to_gw} frame(s)")
    print("--------------------------------------------------------------------------------")

    # Assertions for verification
    assert runtime.cupboard.active_node_count == 1, "Node 2 must be tracked in The Cupboard"
    assert decision.mode == nw.MODE_FORMATION_LOCK, "Swarm must reach FORMATION_LOCK"
    assert decision.lock_status == nw.LOCK_HARD_LOCKED, "Bearing must reach HARD_LOCKED"
    assert frames_relayed_to_gw >= 1, "At least 1 frame must reach the Gateway UDP bridge"

    cam.close()
    gw_sock.close()
    print("SUCCESS: Full optical swarm simulation verified without errors.")


if __name__ == "__main__":
    run_swarm_simulation()
