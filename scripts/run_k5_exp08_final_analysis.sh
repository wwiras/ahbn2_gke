#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke"
PYTHON="/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python"
FORMAL_ROOT="${PROJECT_ROOT}/outputs/k5_exp08_formal-20260902_092321"
LOG="${FORMAL_ROOT}/final_analysis.log"

cd "${PROJECT_ROOT}"
mkdir -p "${FORMAL_ROOT}/final_analysis"
exec > >(tee "${LOG}") 2>&1

echo "K5 Exp08 final local analysis"
echo "formal_root=${FORMAL_ROOT}"
echo "python=${PYTHON}"
"${PYTHON}" --version

export MPLBACKEND=Agg
export MPLCONFIGDIR="/private/tmp/k5_exp08_mplconfig"
export XDG_CACHE_HOME="/private/tmp/k5_exp08_cache"
mkdir -p "${MPLCONFIGDIR}" "${XDG_CACHE_HOME}"

echo "[1/4] Re-run existing K9-style aggregate/validation implementation"
"${PYTHON}" app/k5_exp08_tools.py aggregate "${FORMAL_ROOT}" --mode formal

echo "[2/4] Run independent final scientific audit and analysis"
"${PYTHON}" scripts/k5_exp08_final_science.py "${FORMAL_ROOT}" --project-root "${PROJECT_ROOT}"

echo "[3/4] Static compile check"
"${PYTHON}" -m py_compile app/k5_exp08_tools.py scripts/k5_exp08_final_science.py

echo "[4/4] Confirm final gates"
grep -Fqx "FINAL DATASET AUDIT: PASS" "${LOG}"
grep -Fqx "K5 EXP08 STATUS: FROZEN" "${LOG}"
echo "K5 EXP08 FINAL ANALYSIS: PASS"
