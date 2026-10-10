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

for arg in "$@"; do
    case "$arg" in
        --help|-h)
            echo "Usage: sudo ./install.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --offline, --airgap  Install in DDIL / air-gapped mode using local wheels or debs"
            echo "                       without attempting to contact remote apt or PyPI servers."
            echo "  --skip-deps          Skip all dependency checks/installations."
            echo "  -h, --help           Show this help message and exit."
            echo ""
            echo "Installs Panda Vision Runtime, Protocol Buffers, and bench tools to /opt/neuron-cupboard."
            echo "Registers and enables panda-runtime.service. Auto-detects and installs gateway if colocated."
            echo ""
            echo "Bench diagnostics tool: python3 /opt/neuron-cupboard/scripts/bench_tool.py --help"
            exit 0
            ;;
        --offline|--airgap)
            AIRGAP_MODE=true
            ;;
        --skip-deps)
            SKIP_DEPS=true
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
        echo "[+] Installing system dependencies (python3-opencv, python3-numpy)..."
        if command -v apt-get &>/dev/null; then
            echo "[+] Updating apt package lists (bounded timeout: 15s)..."
            if apt-get update -o Acquire::http::Timeout="15" -o Acquire::https::Timeout="15" -q; then
                echo "[+] Installing packages via apt (no-install-recommends for zero bloat)..."
                apt-get install -y --no-install-recommends python3-opencv python3-numpy python3-pip || true
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
    chmod +x "$INSTALL_DIR/scripts"/*.py 2>/dev/null || true
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

# 6. Install and enable systemd service
if [[ -f "$SCRIPT_DIR/$SERVICE_NAME" ]]; then
    echo "[+] Registering and enabling $SERVICE_NAME..."
    cp "$SCRIPT_DIR/$SERVICE_NAME" "$SYSTEMD_DIR/"
    chmod 644 "$SYSTEMD_DIR/$SERVICE_NAME"
    if command -v systemctl &>/dev/null; then
        systemctl daemon-reload
        systemctl enable "$SERVICE_NAME"
        echo "[+] Panda Runtime installed successfully."
        echo "    To start now: sudo systemctl start $SERVICE_NAME"
        echo "    To view logs: journalctl -u $SERVICE_NAME -f"
    fi
fi

# 7. Auto-detect and configure Tactical Gateway if binary is present
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
    echo "   Bench Diagnostics: python3 $INSTALL_DIR/scripts/bench_tool.py --mode=scan"
fi
echo "================================================================="
