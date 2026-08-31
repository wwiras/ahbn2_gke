#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke"
PYTHON="/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$ROOT/outputs/k5_s0_vs_s5_vs_s6_python/$STAMP"
mkdir -p "$OUT"
exec > >(tee "$OUT/terminal.log") 2>&1
cd "$ROOT"

echo "K5 plain-Python S0 vs S5-f2..f6 vs S6"
echo "Python: $PYTHON"
before_controller="$(shasum -a 256 app/ahbn_controller.py | awk '{print $1}')"
before_peer="$(shasum -a 256 app/peer.py | awk '{print $1}')"
"$PYTHON" -m pytest -q -p no:cacheprovider tests/test_k5_s0_vs_s5_vs_s6_python.py
"$PYTHON" scripts/k5_s0_vs_s5_vs_s6_python.py --output "$OUT/results"
test "$before_controller" = "$(shasum -a 256 app/ahbn_controller.py | awk '{print $1}')"
test "$before_peer" = "$(shasum -a 256 app/peer.py | awk '{print $1}')"
echo "Canonical hash verification: PASS"
echo "Complete: $OUT"
