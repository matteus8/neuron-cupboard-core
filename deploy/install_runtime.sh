#!/usr/bin/env bash
#
# Neuron Cupboard: Panda Edge Runtime Automated Installer
# Target OS: Raspberry Pi OS Lite (64-bit, Debian Bookworm) on Raspberry Pi 5
#

set -euo pipefail

INSTALL_DIR="/opt/neuron-cupboard"
SERVICE_NAME="panda-runtime.service"
SYSTEMD_DIR="/etc/systemd/system"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "================================================================="
echo "   NEURON CUPBOARD: PANDA RUNTIME EDGE INSTALLER (PI 5)"
echo "================================================================="

AIRGAP_MODE=false
SKIP_DEPS=false
GATEWAY_IP=""
GATEWAY_PORT=""
CAMERA_DEVICE="0"
AUTO_START=true

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            echo "Usage: sudo ./install.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --gateway-ip <IP>      Target Tactical Gateway IP for UDP state forwarding."
            echo "  --gateway-port <PORT>  Target Tactical Gateway UDP port (default: 9090)."
            echo "  --device <ID>          Camera device index (default: 0)."
            echo "  --no-start             Register and enable service without immediately starting it."
            echo "  --offline, --airgap    Install in DDIL / air-gapped mode using local wheels or debs"
            echo "                         without attempting to contact remote apt or PyPI servers."
            echo "  --skip-deps            Skip all dependency checks/installations."
            echo "  -h, --help             Show this help message and exit."
            echo ""
            echo "Installs Panda Vision Runtime, Protocol Buffers, and bench tools to /opt/neuron-cupboard."
            echo "Registers and enables panda-runtime.service with automatic libcamera / libcamerify bridge."
            echo "Auto-detects and installs gateway if colocated."
            echo ""
            echo "Bench diagnostics tool: python3 /opt/neuron-cupboard/scripts/bench_tool.py --help"
            exit 0
            ;;
        --offline|--airgap)
            AIRGAP_MODE=true
            shift
            ;;
        --skip-deps)
            SKIP_DEPS=true
            shift
            ;;
        --gateway-ip)
            GATEWAY_IP="$2"
            shift 2
            ;;
        --gateway-port)
            GATEWAY_PORT="$2"
            shift 2
            ;;
        --device)
            CAMERA_DEVICE="$2"
            shift 2
            ;;
        --no-start)
            AUTO_START=false
            shift
            ;;
        *)
            echo "[!] Unknown argument: $1" >&2
            exit 1
            ;;
    esac
done

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

# 2. Check and install dependencies (supports online and air-gapped/DDIL environments)
if [[ "$SKIP_DEPS" == "true" ]]; then
    echo "[+] Skipping dependency installation as requested (--skip-deps)."
elif python3 -c "import cv2, numpy" &>/dev/null; then
    echo "[+] Dependencies verified: OpenCV and NumPy are already available. Skipping network download."
else
    # Auto-detect bundled offline packages
    LOCAL_DEBS=( "$SCRIPT_DIR"/debs/*.deb )
    LOCAL_WHEELS=( "$SCRIPT_DIR"/wheels/*.whl )

    if [[ -f "${LOCAL_DEBS[0]:-}" ]]; then
        echo "[+] Airgap mode: Installing bundled Debian packages from $SCRIPT_DIR/debs..."
        dpkg -i "$SCRIPT_DIR"/debs/*.deb || true
    fi

    if [[ -f "${LOCAL_WHEELS[0]:-}" ]] && command -v pip3 &>/dev/null; then
        echo "[+] Airgap mode: Installing bundled Python wheels from $SCRIPT_DIR/wheels..."
        pip3 install --break-system-packages --no-index --find-links="$SCRIPT_DIR/wheels" -r "$SCRIPT_DIR/requirements.txt" || true
    fi

    # Verify if offline installation satisfied requirements
    if python3 -c "import cv2, numpy" &>/dev/null; then
        echo "[+] Airgap installation successful: OpenCV and NumPy verified."
    elif [[ "$AIRGAP_MODE" == "true" ]]; then
        echo "[!] Error: Running in DDIL/air-gapped mode, but required dependencies (OpenCV/NumPy) are missing." >&2
        echo "    Provide pre-downloaded wheels in $SCRIPT_DIR/wheels/ or debs in $SCRIPT_DIR/debs/." >&2
        exit 1
    else
        # Online installation with bounded timeout and progress visibility
        echo "[+] Installing system dependencies (python3-opencv, python3-numpy, libcamera-tools)..."
        if command -v apt-get &>/dev/null; then
            echo "[+] Updating apt package lists (bounded timeout: 15s)..."
            if apt-get update -o Acquire::http::Timeout="15" -o Acquire::https::Timeout="15" -q; then
                echo "[+] Installing packages via apt (no-install-recommends for zero bloat)..."
                apt-get install -y --no-install-recommends python3-opencv python3-numpy python3-pip libcamera-tools || true
            else
                echo "[!] Warning: apt repository unreachable (offline or constrained DDIL network)." >&2
            fi
        fi

        # Fallback pip install if apt did not provide them and network is available
        if command -v pip3 &>/dev/null && ! python3 -c "import cv2, numpy" &>/dev/null; then
            echo "[+] Attempting pip installation for runtime requirements..."
            pip3 install --break-system-packages -r "$SCRIPT_DIR/requirements.txt" || true
        fi
    fi
fi

# 3. Deploy files to /opt/neuron-cupboard
echo "[+] Installing Panda Runtime to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"

# Copy runtime, proto, scripts, and requirements
cp -r "$SCRIPT_DIR/runtime" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/proto" "$INSTALL_DIR/"
if [[ -d "$SCRIPT_DIR/scripts" ]]; then
    cp -r "$SCRIPT_DIR/scripts" "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/scripts"/*.py "$INSTALL_DIR/scripts"/*.sh 2>/dev/null || true
fi
cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/"
if [[ -d "$SCRIPT_DIR/wheels" ]]; then
    cp -r "$SCRIPT_DIR/wheels" "$INSTALL_DIR/"
fi
if [[ -d "$SCRIPT_DIR/debs" ]]; then
    cp -r "$SCRIPT_DIR/debs" "$INSTALL_DIR/"
fi

# 4. Final verification of runtime environment
if ! python3 -c "import cv2, numpy" &>/dev/null; then
    echo "[!] Warning: OpenCV or NumPy could not be imported. Edge vision may require manual package resolution." >&2
fi

# 5. Set directory permissions
chown -R neuron:neuron "$INSTALL_DIR"
chmod -R 755 "$INSTALL_DIR"

# 6. Configure environment defaults (/etc/default/panda-runtime)
CONFIG_FILE="/etc/default/panda-runtime"
mkdir -p /etc/default
if [[ -n "$GATEWAY_IP" || ! -f "$CONFIG_FILE" ]]; then
    echo "[+] Writing runtime configuration to $CONFIG_FILE..."
    cat <<EOF > "$CONFIG_FILE"
# Neuron Cupboard Panda Runtime Configuration
# Generated by install.sh at $(date -u +"%Y-%m-%dT%H:%M:%SZ")
NEURON_CAMERA_DEVICE=${CAMERA_DEVICE:-0}
NEURON_TARGET_FPS=30.0
NEURON_GATEWAY_IP=${GATEWAY_IP:-}
NEURON_GATEWAY_PORT=${GATEWAY_PORT:-9090}
EOF
    chmod 644 "$CONFIG_FILE"
    echo "    Target Gateway: ${GATEWAY_IP:-disabled (local only)}:${GATEWAY_PORT:-9090}"
elif [[ -f "$CONFIG_FILE" ]]; then
    echo "[+] Preserving existing runtime configuration at $CONFIG_FILE."
fi

# 7. Install and enable systemd service
SERVICE_SRC=""
for s_cand in \
    "$SCRIPT_DIR/$SERVICE_NAME" \
    "$SCRIPT_DIR/systemd/$SERVICE_NAME" \
    "$SCRIPT_DIR/deploy/systemd/$SERVICE_NAME"; do
    if [[ -f "$s_cand" ]]; then
        SERVICE_SRC="$s_cand"
        break
    fi
done

if [[ -n "$SERVICE_SRC" && -f "$SERVICE_SRC" ]]; then
    echo "[+] Registering and enabling $SERVICE_NAME..."
    cp "$SERVICE_SRC" "$SYSTEMD_DIR/$SERVICE_NAME"
    chmod 644 "$SYSTEMD_DIR/$SERVICE_NAME"
    if command -v systemctl &>/dev/null; then
        systemctl daemon-reload
        systemctl enable "$SERVICE_NAME"
        if [[ "$AUTO_START" == "true" ]]; then
            echo "[+] Starting $SERVICE_NAME..."
            systemctl restart "$SERVICE_NAME" || true
            echo "[+] Panda Runtime service active."
            systemctl status "$SERVICE_NAME" --no-pager || true
        else
            echo "[+] Panda Runtime service enabled (deferred start)."
            echo "    To start now: sudo systemctl start $SERVICE_NAME"
        fi
        echo "    To view logs: journalctl -u $SERVICE_NAME -f"
    fi
else
    echo "[!] Warning: $SERVICE_NAME unit file not found." >&2
fi

# 8. Auto-detect and configure Tactical Gateway if binary is present
if [[ -f "$SCRIPT_DIR/install_gateway.sh" ]]; then
    for g_cand in \
        "$SCRIPT_DIR/gateway-linux-arm64" \
        "$SCRIPT_DIR/gateway" \
        "$SCRIPT_DIR/../gateway-linux-arm64" \
        "$(pwd)/gateway-linux-arm64" \
        "$(pwd)/gateway"; do
        if [[ -f "$g_cand" ]]; then
            echo "[+] Detected Gateway binary ($g_cand). Installing Tactical Gateway..."
            bash "$SCRIPT_DIR/install_gateway.sh" "$g_cand" || true
            break
        fi
    done
fi

echo "================================================================="
echo "   INSTALLATION COMPLETE: Node ready for optical reception"
if [[ -f "$INSTALL_DIR/scripts/bench_tool.py" ]]; then
    echo "   Bench Diagnostics: libcamerify python3 $INSTALL_DIR/scripts/bench_tool.py --mode=scan"
fi
echo "================================================================="
