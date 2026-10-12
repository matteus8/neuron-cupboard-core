#!/usr/bin/env bash
#
# Neuron Cupboard: Panda Edge Runtime Daemon Runner
# Target: Raspberry Pi OS Lite (64-bit) on Raspberry Pi 5
# Automatically bridges libcamera/PiSP to V4L2 via libcamerify when available.
#

set -e

# Real-time environment and headless buffers
export PYTHONUNBUFFERED=1
export PYTHONPATH="/opt/neuron-cupboard:${PYTHONPATH:-}"

# Raspberry Pi OS Bookworm with libcamera requires libcamerify for V4L2 compatibility
if command -v libcamerify >/dev/null 2>&1; then
    exec libcamerify /usr/bin/python3 -m runtime.panda.engine "$@"
else
    exec /usr/bin/python3 -m runtime.panda.engine "$@"
fi
