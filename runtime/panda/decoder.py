"""Panda Runtime: Manchester Optical Pulse Decoder.

Decodes optical pulse trains captured by 850nm bandpass-filtered sensors.
Performs clock synchronization, Manchester symbol decoding (IEEE 802.3),
packet framing (preamble + sync word), and bounded CRC-8 verification.
"""

from typing import List, Optional, Tuple, Deque
from collections import deque
import proto.neuron_wire as nw


class ManchesterDecoder:
    """Deterministic stream decoder for Manchester-modulated optical pulses."""

    def __init__(self, polarity: int = 0):
        # 0 = IEEE 802.3, 1 = Thomas
        self.polarity = polarity
        self.chip_history: Deque[int] = deque(maxlen=256)
        self.bit_stream: Deque[int] = deque(maxlen=128)

    def reset(self):
        self.chip_history.clear()
        self.bit_stream.clear()

    def feed_chip(self, chip: int) -> Optional[int]:
        """Feed a single half-bit chip (0 or 1).

        Returns decoded bit (0 or 1) if a valid transition occurred, else None.
        """
        chip_val = 1 if chip else 0
        self.chip_history.append(chip_val)

        if len(self.chip_history) < 2:
            return None

        # Look at the last two chips
        c1 = self.chip_history[-2]
        c2 = self.chip_history[-1]

        # Only process on even boundaries or valid pairs
        # In IEEE 802.3: (1, 0) -> 0; (0, 1) -> 1
        if self.polarity == 0:
            if c1 == 1 and c2 == 0:
                bit = 0
            elif c1 == 0 and c2 == 1:
                bit = 1
            else:
                # Manchester transition violation
                return None
        else:
            if c1 == 0 and c2 == 1:
                bit = 0
            elif c1 == 1 and c2 == 0:
                bit = 1
            else:
                return None

        # Clear processed pair
        self.chip_history.clear()
        self.bit_stream.append(bit)
        return bit

    def feed_chips(self, chips: List[int]) -> List[nw.WireFrame]:
        """Process a sequence of half-bit chips and extract any completed frames."""
        valid_frames: List[nw.WireFrame] = []
        for chip in chips:
            self.feed_chip(chip)
            frame = self._try_extract_frame()
            if frame:
                valid_frames.append(frame)
        return valid_frames

    def _try_extract_frame(self) -> Optional[nw.WireFrame]:
        """Scan accumulated bitstream for a complete 6-byte wire frame (48 bits)."""
        if len(self.bit_stream) < 48:
            return None

        # Need 48 bits for a 6-byte frame
        bits = list(self.bit_stream)

        # Slide through bitstream looking for 0xAA (preamble) and 0xD5 (sync word)
        for offset in range(len(bits) - 47):
            # Check preamble (0xAA = 10101010b)
            preamble_byte = self._bits_to_byte(bits[offset : offset + 8])
            if preamble_byte != nw.PREAMBLE:
                continue

            # Check sync word (0xD5 = 11010101b)
            sync_byte = self._bits_to_byte(bits[offset + 8 : offset + 16])
            if sync_byte != nw.SYNC_WORD:
                continue

            # Candidate frame found, assemble remaining 4 bytes
            frame_bytes = bytearray()
            frame_bytes.append(preamble_byte)
            frame_bytes.append(sync_byte)

            for b_idx in range(2, 6):
                start = offset + (b_idx * 8)
                byte_val = self._bits_to_byte(bits[start : start + 8])
                frame_bytes.append(byte_val)

            # Validate frame
            valid, wire_frame = nw.unpack_frame(bytes(frame_bytes))
            if valid:
                # Consume matched bits up to end of this frame
                consume_count = offset + 48
                for _ in range(consume_count):
                    if self.bit_stream:
                        self.bit_stream.popleft()
                return wire_frame

        return None

    @staticmethod
    def _bits_to_byte(bits: List[int]) -> int:
        val = 0
        for bit in bits:
            val = (val << 1) | (1 if bit else 0)
        return val & 0xFF

    def get_bitstream_hex(self) -> str:
        """Convert current bitstream to hex bytes string for live diagnostics."""
        bits = list(self.bit_stream)
        bytes_list = []
        for i in range(0, len(bits) - 7, 8):
            val = self._bits_to_byte(bits[i : i + 8])
            bytes_list.append(f"{val:02X}")
        return " ".join(bytes_list)

    def inspect_stream(self) -> dict:
        """Inspect bitstream for framing markers and diagnostic health."""
        bits = list(self.bit_stream)
        hex_str = self.get_bitstream_hex()
        preamble_found = False
        sync_found = False
        crc_err = None

        for offset in range(len(bits) - 47):
            p = self._bits_to_byte(bits[offset : offset + 8])
            if p == nw.PREAMBLE:
                preamble_found = True
                s = self._bits_to_byte(bits[offset + 8 : offset + 16])
                if s == nw.SYNC_WORD:
                    sync_found = True
                    payload = bytes([self._bits_to_byte(bits[offset + 16 + i * 8 : offset + 24 + i * 8]) for i in range(3)])
                    c = self._bits_to_byte(bits[offset + 40 : offset + 48])
                    exp = nw.crc8(payload)
                    if c != exp:
                        crc_err = f"got 0x{c:02X}, expected 0x{exp:02X}"
                    break

        return {
            "bit_count": len(bits),
            "hex": hex_str,
            "preamble_found": preamble_found,
            "sync_found": sync_found,
            "crc_err": crc_err,
        }
