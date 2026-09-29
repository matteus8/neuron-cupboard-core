"""Panda Runtime: Deterministic Serial/UART Hardware Bridge.

Interfaces Raspberry Pi 5 edge compute to the RP2040 microcontroller optical transmitter
over high-speed UART (e.g. /dev/ttyAMA0 @ 921600 baud).
Enforces non-blocking timeouts to prevent execution hangs in harsh RF-denied environments.
Includes an in-memory loopback simulator for host testing without MCU hardware.
"""

import time
from typing import Optional, Tuple
import proto.neuron_wire as nw

try:
    import serial
    HAVE_PYSERIAL = True
except ImportError:
    HAVE_PYSERIAL = False


class SerialBridge:
    """Non-blocking deterministic serial interface to the RP2040 optical payload."""

    def __init__(
        self,
        port: str = "/dev/ttyAMA0",
        baudrate: int = 921600,
        timeout_sec: float = 0.05,
        simulate: bool = False,
    ):
        self.port = port
        self.baudrate = baudrate
        self.timeout_sec = timeout_sec
        self.simulate = simulate or not HAVE_PYSERIAL

        self.ser = None
        self.simulated_tx_queue = []
        self.simulated_rx_queue = []

        if not self.simulate:
            try:
                self.ser = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=self.timeout_sec,
                    write_timeout=self.timeout_sec,
                )
            except Exception:
                # Fallback to simulation if device is unavailable
                self.simulate = True
                self.ser = None

    def send_wire_frame(self, frame_bytes: bytes) -> bool:
        """Transmit 6-byte optical packet to RP2040 for physical IR emission."""
        if len(frame_bytes) != nw.FRAME_LEN:
            return False

        if self.simulate or self.ser is None:
            self.simulated_tx_queue.append(frame_bytes)
            return True

        try:
            bytes_written = self.ser.write(frame_bytes)
            return bytes_written == len(frame_bytes)
        except Exception as e:
            now_us = int(time.time() * 1_000_000)
            print(f"level=ERROR ts={now_us} event=serial_tx_failed err={e}")
            return False

    def read_wire_frame(self) -> Optional[nw.WireFrame]:
        """Read 6-byte optical telemetry packet from RP2040 with non-blocking timeout."""
        if self.simulate or self.ser is None:
            if self.simulated_rx_queue:
                raw = self.simulated_rx_queue.pop(0)
                valid, wf = nw.unpack_frame(raw)
                return wf if valid else None
            return None

        try:
            # Deterministic bounded read: exactly 6 bytes
            raw = self.ser.read(nw.FRAME_LEN)
            if len(raw) == nw.FRAME_LEN:
                valid, wf = nw.unpack_frame(raw)
                if valid:
                    return wf
            return None
        except Exception as e:
            now_us = int(time.time() * 1_000_000)
            print(f"level=WARN ts={now_us} event=serial_rx_timeout err={e}")
            return None

    def close(self):
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None
