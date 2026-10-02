#!/usr/bin/env bash
#
# Neuron Cupboard: Panda Edge Runtime Automated Installer
# Target OS: Raspberry Pi OS Lite (64-bit, Debian Bookworm) on Raspberry Pi 5
#

set -euo pipefail

INSTALL_DIR="/opt/neuron-cupboard"
SERVICE_NAME="panda-runtime.service"
SYSTEMD_DIR="/etc/systemd/system"

echo "================================================================="
echo "   NEURON CUPBOARD: PANDA RUNTIME EDGE INSTALLER (PI 5)"
echo "================================================================="

if [[ $EUID -ne 0 ]]; then
   echo "[!] Error: This script must be run as root (use sudo ./install.sh)" >&2
   exit 1
fi

# 1. Create system user and assign hardware groups (video for CSI camera, dialout for UART)
echo "[+] Configuring system service user 'neuron'..."
if ! id "neuron" &>/dev/null; then
    useradd -r -s /usr/sbin/nologin -d "$INSTALL_DIR" neuron
fi
usermod -aG video,dialout neuron 2>/dev/null || true

# 2. Install hardware-accelerated system dependencies on Debian/Raspberry Pi OS
if command -v apt-get &>/dev/null; then
    echo "[+] Installing system dependencies (python3-opencv, python3-numpy)..."
    apt-get update -qq && apt-get install -y -qq python3-opencv python3-numpy python3-pip || true
fi

# 3. Deploy files to /opt/neuron-cupboard
echo "[+] Installing Panda Runtime to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Copy runtime, proto, and requirements
cp -r "$SCRIPT_DIR/runtime" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/proto" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/"

# 4. Fallback pip install if needed
if command -v pip3 &>/dev/null && ! python3 -c "import cv2, numpy" &>/dev/null; then
    echo "[+] Installing Python dependencies via pip..."
    pip3 install --break-system-packages -q -r "$INSTALL_DIR/requirements.txt" || true
fi

# 5. Set directory permissions
chown -R neuron:neuron "$INSTALL_DIR"
chmod -R 755 "$INSTALL_DIR"

# 6. Install and enable systemd service
if [[ -f "$SCRIPT_DIR/$SERVICE_NAME" ]]; then
    echo "[+] Registering and enabling $SERVICE_NAME..."
    cp "$SCRIPT_DIR/$SERVICE_NAME" "$SYSTEMD_DIR/"
    if command -v systemctl &>/dev/null; then
        systemctl daemon-reload
        systemctl enable "$SERVICE_NAME"
        echo "[+] Panda Runtime installed successfully."
        echo "    To start now: sudo systemctl start $SERVICE_NAME"
        echo "    To view logs: journalctl -u $SERVICE_NAME -f"
    fi
fi

echo "================================================================="
echo "   INSTALLATION COMPLETE: Node ready for optical reception"
echo "================================================================="
