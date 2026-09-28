#!/usr/bin/env bash
# Deterministic compilation script for neuron.proto schemas across Go, Python, and C.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "${SCRIPT_DIR}")"

export PATH="${HOME}/go/bin:${PATH}"

echo "==> Compiling Protocol Buffers from ${SCRIPT_DIR}/neuron.proto..."

# 1. Generate Go package
mkdir -p "${SCRIPT_DIR}/gen/go"
protoc \
    --proto_path="${SCRIPT_DIR}" \
    --go_out="${SCRIPT_DIR}/gen/go" \
    --go_opt=paths=source_relative \
    "${SCRIPT_DIR}/neuron.proto"
echo "  [OK] Go bindings generated in proto/gen/go/"

# 2. Generate Python bindings
mkdir -p "${SCRIPT_DIR}/gen/py"
protoc \
    --proto_path="${SCRIPT_DIR}" \
    --python_out="${SCRIPT_DIR}/gen/py" \
    "${SCRIPT_DIR}/neuron.proto"
echo "  [OK] Python bindings generated in proto/gen/py/"

# 3. Synchronize C bare-metal header to include/
mkdir -p "${SCRIPT_DIR}/c"
cp "${SCRIPT_DIR}/neuron_wire.h" "${SCRIPT_DIR}/c/neuron_wire.h"
echo "  [OK] C bare-metal header synchronized to proto/c/"

echo "==> Protobuf code generation complete."
