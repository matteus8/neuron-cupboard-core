#!/usr/bin/env bash
#
# Neuron Cupboard: Tactical Zenoh Gateway Automated Installer
# Target OS: Raspberry Pi OS Lite (64-bit, Debian Bookworm) on Raspberry Pi 5 / ARM64 Tactical Nodes
#

set -euo pipefail

INSTALL_DIR="/opt/neuron-cupboard"
BIN_DIR="$INSTALL_DIR/bin"
SERVICE_NAME="neuron-gateway.service"
SYSTEMD_DIR="/etc/systemd/system"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "================================================================="
echo "   NEURON CUPBOARD: TACTICAL ZENOH GATEWAY INSTALLER (ARM64)"
echo "================================================================="

if [[ $EUID -ne 0 ]]; then
   echo "[!] Error: This script must be run as root (use sudo ./install_gateway.sh)" >&2
   exit 1
fi

# 1. Locate the compiled gateway binary
SRC_BIN="${1:-}"
if [[ -z "$SRC_BIN" ]]; then
    for candidate in \
        "$SCRIPT_DIR/gateway-linux-arm64" \
        "$SCRIPT_DIR/gateway" \
        "$SCRIPT_DIR/../gateway-linux-arm64" \
        "$SCRIPT_DIR/bin/gateway-linux-arm64" \
        "$SCRIPT_DIR/bin/gateway" \
        "$(pwd)/gateway-linux-arm64" \
        "$(pwd)/gateway"; do
        if [[ -f "$candidate" ]]; then
            SRC_BIN="$candidate"
            break
        fi
    done
fi

if [[ -z "$SRC_BIN" || ! -f "$SRC_BIN" ]]; then
    echo "[!] Error: Gateway binary not found." >&2
    echo "    Please specify the binary path: sudo ./install_gateway.sh <path/to/gateway-linux-arm64>" >&2
    exit 1
fi

echo "[+] Located Gateway binary: $SRC_BIN"

# 2. Configure system service user 'neuron'
echo "[+] Configuring system service user 'neuron'..."
if ! id "neuron" &>/dev/null; then
    useradd -r -s /usr/sbin/nologin -d "$INSTALL_DIR" neuron
fi

# 3. Deploy binary to /opt/neuron-cupboard/bin/gateway
echo "[+] Installing Gateway binary to $BIN_DIR/gateway..."
mkdir -p "$BIN_DIR"
cp "$SRC_BIN" "$BIN_DIR/gateway"
chmod 755 "$BIN_DIR/gateway"
chown -R neuron:neuron "$INSTALL_DIR"

# 4. Deploy default environment file if missing
if [[ ! -f "/etc/default/neuron-gateway" ]]; then
    echo "[+] Writing default configuration to /etc/default/neuron-gateway..."
    cat <<'EOF' > /etc/default/neuron-gateway
# Neuron Cupboard Tactical Zenoh Gateway Configuration
NEURON_ZENOH_ROUTER=tcp/127.0.0.1:7447
NEURON_LISTEN_ADDR=127.0.0.1:9090
NEURON_METRICS_ADDR=127.0.0.1:9093
EOF
    chmod 644 /etc/default/neuron-gateway
fi

# 5. Install and enable systemd service
SERVICE_SRC=""
for s_candidate in \
    "$SCRIPT_DIR/$SERVICE_NAME" \
    "$SCRIPT_DIR/systemd/$SERVICE_NAME" \
    "$SCRIPT_DIR/deploy/systemd/$SERVICE_NAME"; do
    if [[ -f "$s_candidate" ]]; then
        SERVICE_SRC="$s_candidate"
        break
    fi
done

if [[ -n "$SERVICE_SRC" && -f "$SERVICE_SRC" ]]; then
    echo "[+] Registering and enabling $SERVICE_NAME..."
    cp "$SERVICE_SRC" "$SYSTEMD_DIR/"
    chmod 644 "$SYSTEMD_DIR/$SERVICE_NAME"
    if command -v systemctl &>/dev/null; then
        systemctl daemon-reload
        systemctl enable "$SERVICE_NAME"
        systemctl restart "$SERVICE_NAME" || true
        echo "[+] Tactical Gateway installed and service active."
        echo "    To check status: sudo systemctl status $SERVICE_NAME"
        echo "    To view logs:   journalctl -u $SERVICE_NAME -f"
        echo "    Health check:   curl http://127.0.0.1:9093/healthz"
    fi
else
    echo "[!] Warning: $SERVICE_NAME not found in search paths. Binary installed to $BIN_DIR/gateway."
fi

echo "================================================================="
echo "   GATEWAY INSTALLATION COMPLETE: Tactical Zenoh bridge ready"
echo "================================================================="
