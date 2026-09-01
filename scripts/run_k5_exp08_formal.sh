#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"
if [ "$#" -ne 2 ] || [ "$1" != "--smoke-report" ]; then
  echo "Usage: IMAGE=<image> $0 --smoke-report outputs/k5_exp08_smoke-<timestamp>/terminal.log" >&2
  exit 2
fi
SMOKE_REPORT="$2"
grep -Fxq "K5 EXP08 SMOKE GATE: PASS" "${SMOKE_REPORT}" || {
  echo "ERROR: formal disabled because smoke PASS is absent: ${SMOKE_REPORT}" >&2
  exit 1
}
STAMP="$(date +%Y%m%d_%H%M%S)"
K5_ROOT="${K5_ROOT:-${ROOT_DIR}/outputs/k5_exp08_formal-${STAMP}}"
echo "COMMAND: IMAGE=${IMAGE:-<required>} $0 --smoke-report ${SMOKE_REPORT}"
K5_ROOT="${K5_ROOT}" scripts/run_k5_exp08.sh formal
