#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke"
PYTHON="/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$ROOT/outputs/k5_shortest_actuator_solution/$STAMP"
mkdir -p "$OUT"
exec > >(tee "$OUT/terminal.log") 2>&1

cd "$ROOT"
echo "K5 shortest actuator screening"
echo "Python: $PYTHON"
"$PYTHON" -m pytest -q -p no:cacheprovider tests/test_k5_shortest_actuator_screening.py
before_controller="$(shasum -a 256 app/ahbn_controller.py | awk '{print $1}')"
before_peer="$(shasum -a 256 app/peer.py | awk '{print $1}')"
test "$before_controller" = "dee8cb8e81494bc1448793076803a330602d613e9654ac7fa572d8203f6cc7c8"
test "$before_peer" = "64c529f9c32f732c8d4f2c5959c75c0bbed20252328b81b018eb35c6cef10b5a"
"$PYTHON" scripts/k5_shortest_actuator_screening.py --output "$OUT/results"
after_controller="$(shasum -a 256 app/ahbn_controller.py | awk '{print $1}')"
after_peer="$(shasum -a 256 app/peer.py | awk '{print $1}')"
test "$before_controller" = "$after_controller"
test "$before_peer" = "$after_peer"
echo "Canonical hash verification: PASS"
echo "Complete: $OUT"
