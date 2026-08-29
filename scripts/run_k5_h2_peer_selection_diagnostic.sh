#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"
PYTHON="/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python"
NAMESPACE="ahbn-k5-h2"
RELEASE="ahbn"
EXPECTED_CONTEXT="gke_stoked-cosine-415611_us-central1-a_bcgossip-cluster"
IMAGE=""

usage() {
  echo "Usage: $0 --image <temporary-k5-h2diag-image> [--expected-context <context>] [--namespace <namespace>]" >&2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --image) IMAGE="${2:-}"; shift 2 ;;
    --expected-context) EXPECTED_CONTEXT="${2:-}"; shift 2 ;;
    --namespace) NAMESPACE="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

if [ -z "${IMAGE}" ]; then
  echo "ERROR: --image is required; no canonical/default image is permitted" >&2
  exit 2
fi
case "${IMAGE}" in
  *:k5-h2diag-*) ;;
  *) echo "ERROR: image must use an explicit temporary :k5-h2diag-* tag" >&2; exit 2 ;;
esac
case "${IMAGE}" in
  *:latest|*:v5|*:v6|*:v7) echo "ERROR: canonical/frozen image tag is forbidden" >&2; exit 2 ;;
esac
if [ ! -x "${PYTHON}" ]; then
  echo "ERROR: required Python is not executable: ${PYTHON}" >&2
  exit 1
fi
for command in kubectl helm; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "ERROR: required command not found: ${command}" >&2
    exit 1
  fi
done

CURRENT_CONTEXT="$(kubectl config current-context)"
if [ "${CURRENT_CONTEXT}" != "${EXPECTED_CONTEXT}" ]; then
  echo "ERROR: kubectl context mismatch" >&2
  echo "  expected: ${EXPECTED_CONTEXT}" >&2
  echo "  current:  ${CURRENT_CONTEXT}" >&2
  exit 1
fi
if ! [[ "${NAMESPACE}" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]]; then
  echo "ERROR: invalid Kubernetes namespace: ${NAMESPACE}" >&2
  exit 2
fi

echo "K5 H2 PEER-SELECTION DIAGNOSTIC"
echo "CANONICAL FANOUT 2/3/4"
echo "SEEDS 42,44"
echo "1 REP EACH"
echo "TOTAL RUNS = 2"
echo "TEMPORARY DIAGNOSTIC IMAGE = ${IMAGE}"
echo "FORMAL K5 WILL NOT RUN"
echo "KUBECTL CONTEXT = ${CURRENT_CONTEXT}"
echo "NAMESPACE = ${NAMESPACE}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT_ROOT="${ROOT_DIR}/outputs/k5_h2_peer_selection-${STAMP}"
CONFIG_DIR="${OUTPUT_ROOT}/configs"
LOG_DIR="${OUTPUT_ROOT}/logs"
mkdir -p "${CONFIG_DIR}" "${LOG_DIR}"
exec > >(tee -a "${LOG_DIR}/runner.log") 2>&1

TOPOLOGY_BACKUP="${LOG_DIR}/helm_topology_before.json"
cp "${ROOT_DIR}/helm/ahbn/topology.json" "${TOPOLOGY_BACKUP}"
restore_topology() {
  cp "${TOPOLOGY_BACKUP}" "${ROOT_DIR}/helm/ahbn/topology.json"
}
trap restore_topology EXIT

"${PYTHON}" - "${OUTPUT_ROOT}/metadata.json" "${IMAGE}" "${CURRENT_CONTEXT}" "${NAMESPACE}" "${STAMP}" <<'PY'
import json, subprocess, sys
path, image, context, namespace, stamp = sys.argv[1:]
metadata = {
    "diagnostic": "K5 H2 peer selection",
    "created_utc": stamp,
    "image": image,
    "kubectl_context": context,
    "namespace": namespace,
    "strategy": "ahbn",
    "num_nodes": 20,
    "topology": "ba",
    "ba_m": 2,
    "source_peer": 0,
    "seeds": [42, 44],
    "repetitions_per_seed": 1,
    "messages": 20,
    "message_interval_seconds": 0.4,
    "overload_factor": 2.0,
    "overload_delay_ms": 1400,
    "settlement_seconds": 18,
    "canonical_fanout": [2, 3, 4],
    "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
}
with open(path, "w", encoding="utf-8") as handle:
    json.dump(metadata, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY

for seed in 42 44; do
  RUN_ID="k5_ahbn_seed${seed}_factor2.0"
  CONFIG_PATH="${CONFIG_DIR}/${RUN_ID}.yaml"
  SEED_DIR="${OUTPUT_ROOT}/seed${seed}"
  RAW_DIR="${SEED_DIR}/raw"
  mkdir -p "${RAW_DIR}"
  "${PYTHON}" "${ROOT_DIR}/app/k5_exp08_tools.py" config \
    --base "${ROOT_DIR}/experiments/k5_exp08_ahbn.yaml" \
    --out "${CONFIG_PATH}" --algorithm ahbn --seed "${seed}" --factor 2.0
  RELATIVE_CONFIG="${CONFIG_PATH#${ROOT_DIR}/}"
  echo "=== H2 SEED ${seed}: SINGLE RUN START ==="
  OUTDIR="${RAW_DIR}" NAMESPACE="${NAMESPACE}" RELEASE="${RELEASE}" \
    IMAGE="${IMAGE}" PYTHON="${PYTHON}" SKIP_PLOT=1 POD_MANAGEMENT_POLICY=Parallel \
    "${ROOT_DIR}/scripts/run_experiment.sh" "${RELATIVE_CONFIG}"
  echo "=== H2 SEED ${seed}: SINGLE RUN COMPLETE ==="
done

"${PYTHON}" "${ROOT_DIR}/scripts/k5_h2_peer_selection_analysis.py" \
  --root "${OUTPUT_ROOT}"

trap - EXIT
restore_topology
echo "K5 H2 diagnostic complete: ${OUTPUT_ROOT}"
echo "No automatic reruns were performed."
