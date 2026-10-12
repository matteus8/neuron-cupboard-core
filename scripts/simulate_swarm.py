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

    # 2. Prepare transmission sequences for Remote Bamboo Nodes 2 & 3
    # Node 2: Formation lock, consensus ACK
    node2_state = nw.pack_state(
        mode=nw.MODE_SEARCH,
        lock_status=nw.LOCK_TRACKING,
        consensus_ack=True,
    )
    node2_frame_bytes = nw.pack_frame(node_id=2, seq_num=1, state_byte=node2_state)

    # Node 3: Formation lock, consensus ACK
    node3_state = nw.pack_state(
        mode=nw.MODE_SEARCH,
        lock_status=nw.LOCK_TRACKING,
        consensus_ack=True,
    )
    node3_frame_bytes = nw.pack_frame(node_id=3, seq_num=2, state_byte=node3_state)

    def to_chips(frame_bytes):
        chips = []
        for b in frame_bytes:
            for bit_pos in range(7, -1, -1):
                bit = (b >> bit_pos) & 1
                if bit == 0:
                    chips.extend([1, 0])
                else:
                    chips.extend([0, 1])
        return chips

    node2_chips = to_chips(node2_frame_bytes)
    node3_chips = to_chips(node3_frame_bytes)

    print(f"level=INFO event=multi_node_frames_prepared nodes=[2,3] chips_per_node=96")

    # 3. Simulate optical frames:
    # Node 2 pulses at pixel (100, 120) [bearing left]
    # Node 3 pulses at pixel (220, 120) [bearing right]
    frames_relayed_to_gw = 0

    print("level=INFO event=starting_concurrent_spatial_pulse_modulation...")
    for chip_idx in range(96):
        c2_lit = (node2_chips[chip_idx] == 1)
        c3_lit = (node3_chips[chip_idx] == 1)

        active_emitters = [
            (100.0, 120.0, 5.0, 245.0, c2_lit),
            (220.0, 120.0, 5.0, 245.0, c3_lit),
        ]

        frame = cam.grab_frame(active_emitters=active_emitters)
        if frame:
            extracted = runtime.process_optical_frame(
                frame.data,
                width=frame.width,
                height=frame.height,
            )
            for f in extracted:
                print(f"level=INFO chip={chip_idx} event=frame_recovered node={f.node_id} seq={f.seq_num}")

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
    for nid, node_st in runtime.cupboard.nodes.items():
        print(f"    - Swarm Node {nid}: mode={node_st.state.mode} az_mrad={node_st.azimuth_mrad} ack={node_st.state.consensus_ack}")
    print("--------------------------------------------------------------------------------")

    # Assertions for verification
    assert runtime.cupboard.active_node_count == 2, "Both Node 2 and Node 3 must be tracked in The Cupboard"
    assert decision.mode == nw.MODE_FORMATION_LOCK, "Swarm must reach FORMATION_LOCK"
    assert decision.lock_status == nw.LOCK_HARD_LOCKED, "Bearing must reach HARD_LOCKED"
    assert frames_relayed_to_gw >= 2, "At least 2 frames must reach the Gateway UDP bridge"

    cam.close()
    gw_sock.close()
    print("SUCCESS: Full optical swarm simulation verified without errors.")


if __name__ == "__main__":
    run_swarm_simulation()
