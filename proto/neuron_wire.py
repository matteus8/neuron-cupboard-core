"""Neuron Wire Protocol Codec (Pure Python / MicroPython compatible).

Implements the physical 6-byte wire frame layout, 8-bit discrete state vector
bitmask packing/unpacking, and deterministic CRC-8-CCITT calculations for the
Neuron Cupboard 850nm IR optical link.
"""

from typing import Tuple, NamedTuple

PREAMBLE: int = 0xAA
SYNC_WORD: int = 0xD5
FRAME_LEN: int = 6

# State vector bitmask constants
STATE_MODE_MASK: int = 0x03
STATE_MODE_SHIFT: int = 0
STATE_LOCK_MASK: int = 0x0C
STATE_LOCK_SHIFT: int = 2
STATE_CONSENSUS_ACK: int = 0x10
STATE_PROXIMITY_ALERT: int = 0x20
STATE_SWAP_CRITICAL: int = 0x40
STATE_SYNC_MARKER: int = 0x80

# Operational modes (Bits 0-1)
MODE_UNSPECIFIED: int = 0
MODE_SEARCH: int = 1
MODE_FORMATION_LOCK: int = 2
MODE_DISPERSAL: int = 3

# Bearing lock status (Bits 2-3)
LOCK_NONE: int = 0
LOCK_ACQUIRING: int = 1
LOCK_TRACKING: int = 2
LOCK_HARD_LOCKED: int = 3


class DiscreteState(NamedTuple):
    mode: int
    lock_status: int
    consensus_ack: bool
    proximity_alert: bool
    swap_critical: bool
    sync_marker: bool


class WireFrame(NamedTuple):
    node_id: int
    seq_num: int
    state_byte: int
    state: DiscreteState
    crc8: int


def crc8_update(crc: int, byte_val: int) -> int:
    """CRC-8-CCITT (Polynomial 0x07, Initial 0x00)."""
    crc ^= (byte_val & 0xFF)
    for _ in range(8):
        if crc & 0x80:
            crc = ((crc << 1) ^ 0x07) & 0xFF
        else:
            crc = (crc << 1) & 0xFF
    return crc


def crc8(data: bytes) -> int:
    """Calculate CRC-8 over a bytes sequence."""
    val = 0x00
    for b in data:
        val = crc8_update(val, b)
    return val


def pack_state(
    mode: int,
    lock_status: int,
    consensus_ack: bool = False,
    proximity_alert: bool = False,
    swap_critical: bool = False,
    sync_marker: bool = False,
) -> int:
    """Pack discrete fields into single 8-bit discrete state vector."""
    state = 0
    state |= (mode & 0x03) << STATE_MODE_SHIFT
    state |= (lock_status & 0x03) << STATE_LOCK_SHIFT
    if consensus_ack:
        state |= STATE_CONSENSUS_ACK
    if proximity_alert:
        state |= STATE_PROXIMITY_ALERT
    if swap_critical:
        state |= STATE_SWAP_CRITICAL
    if sync_marker:
        state |= STATE_SYNC_MARKER
    return state & 0xFF


def unpack_state(state_byte: int) -> DiscreteState:
    """Unpack 8-bit discrete state vector into structured DiscreteState."""
    b = state_byte & 0xFF
    return DiscreteState(
        mode=(b & STATE_MODE_MASK) >> STATE_MODE_SHIFT,
        lock_status=(b & STATE_LOCK_MASK) >> STATE_LOCK_SHIFT,
        consensus_ack=bool(b & STATE_CONSENSUS_ACK),
        proximity_alert=bool(b & STATE_PROXIMITY_ALERT),
        swap_critical=bool(b & STATE_SWAP_CRITICAL),
        sync_marker=bool(b & STATE_SYNC_MARKER),
    )


def pack_frame(node_id: int, seq_num: int, state_byte: int) -> bytes:
    """Pack a 6-byte wire frame with preamble, sync word, and CRC-8."""
    payload = bytes([node_id & 0xFF, seq_num & 0xFF, state_byte & 0xFF])
    chksum = crc8(payload)
    return bytes([PREAMBLE, SYNC_WORD, node_id & 0xFF, seq_num & 0xFF, state_byte & 0xFF, chksum])


def unpack_frame(raw_bytes: bytes) -> Tuple[bool, WireFrame]:
    """Validate and unpack a 6-byte wire frame.

    Returns (is_valid, WireFrame).
    """
    if len(raw_bytes) != FRAME_LEN:
        return False, None
    if raw_bytes[0] != PREAMBLE or raw_bytes[1] != SYNC_WORD:
        return False, None

    node_id = raw_bytes[2]
    seq_num = raw_bytes[3]
    state_byte = raw_bytes[4]
    frame_crc = raw_bytes[5]

    expected_crc = crc8(raw_bytes[2:5])
    if frame_crc != expected_crc:
        return False, None

    state = unpack_state(state_byte)
    return True, WireFrame(
        node_id=node_id,
        seq_num=seq_num,
        state_byte=state_byte,
        state=state,
        crc8=frame_crc,
    )
