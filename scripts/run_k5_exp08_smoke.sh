#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"
STAMP="$(date +%Y%m%d_%H%M%S)"
K5_ROOT="${K5_ROOT:-${ROOT_DIR}/outputs/k5_exp08_smoke-${STAMP}}"
echo "COMMAND: IMAGE=${IMAGE:-<required>} $0"
K5_ROOT="${K5_ROOT}" scripts/run_k5_exp08.sh smoke
