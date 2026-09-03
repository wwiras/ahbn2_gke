#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "${ROOT_DIR}"
REQUIRED_PYTHON="/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python"; PYTHON="${PYTHON:-${REQUIRED_PYTHON}}"
IMAGE="${IMAGE:-}"; MODE="${1:-}"; EXPECTED_CONTEXT="${EXPECTED_CONTEXT:-gke_stoked-cosine-415611_us-central1-a_bcgossip-cluster}"
NAMESPACE="${NAMESPACE:-ahbn-k5-exp10}"; RELEASE="${RELEASE:-ahbn}"; STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
CURRENT_STAGE="preflight"; CURRENT_SEED="N/A"; CURRENT_TREATMENT="N/A"
fail(){ echo "ERROR: $*" >&2; exit 1; }
on_error(){ local status=$?; echo "FAILED stage=${CURRENT_STAGE} seed=${CURRENT_SEED} treatment=${CURRENT_TREATMENT} status=${status}" >&2; echo "output=${RESULT_ROOT:-not-created}" >&2; exit "${status}"; }
trap on_error ERR
[ "${MODE}" = smoke ] || [ "${MODE}" = formal ] || fail "Usage: IMAGE=... $0 smoke|formal"
[ -x "${PYTHON}" ] && [ "${PYTHON}" = "${REQUIRED_PYTHON}" ] || fail "required Python mismatch: ${PYTHON}"
[ -n "${IMAGE}" ] || fail "IMAGE must name the manually built Exp10 image"
for name in kubectl helm shasum; do command -v "${name}" >/dev/null || fail "missing command: ${name}"; done
[ "$(kubectl config current-context)" = "${EXPECTED_CONTEXT}" ] || fail "unexpected kubectl context"
kubectl auth can-i delete pods -n "${NAMESPACE}" | grep -qx yes || fail "pod-delete authorization unavailable"
if [ "${MODE}" = smoke ]; then DEFAULT_ROOT="${ROOT_DIR}/outputs/k5_exp10_smoke-${STAMP}"; seeds=(42); else DEFAULT_ROOT="${ROOT_DIR}/outputs/k5_exp10-${STAMP}"; seeds=(42 43 44 45 46); fi
RESULT_ROOT="${RESULT_ROOT:-${DEFAULT_ROOT}}"; mkdir -p "${RESULT_ROOT}"/{configs,generated,runs,results,raw}
exec > >(tee -a "${RESULT_ROOT}/terminal.log") 2>&1
printf '%s\n' "${IMAGE}" >"${RESULT_ROOT}/image.txt"; git rev-parse HEAD >"${RESULT_ROOT}/git_commit.txt"
shasum -a 256 app/ahbn_controller.py app/peer.py >"${RESULT_ROOT}/canonical_hashes_before.txt"
[ "$(awk 'NR==1{print $1}' "${RESULT_ROOT}/canonical_hashes_before.txt")" = dee8cb8e81494bc1448793076803a330602d613e9654ac7fa572d8203f6cc7c8 ] || fail "canonical controller changed"
[ "$(awk 'NR==2{print $1}' "${RESULT_ROOT}/canonical_hashes_before.txt")" = 64c529f9c32f732c8d4f2c5959c75c0bbed20252328b81b018eb35c6cef10b5a ] || fail "canonical peer changed"
"${PYTHON}" -m pytest -q tests/test_k5_exp10.py tests/test_k5_final_actuator_gke.py
algorithms=(gossip structured dcsoc ahbn)
for seed in "${seeds[@]}"; do
  generated=()
  for algorithm in "${algorithms[@]}"; do
    config="${RESULT_ROOT}/configs/${algorithm}_seed${seed}.yaml"; topology="${RESULT_ROOT}/generated/${algorithm}_seed${seed}.json"
    "${PYTHON}" app/k5_exp10_tools.py config --base experiments/exp10.yaml --out "${config}" --algorithm "${algorithm}" --seed "${seed}"
    "${PYTHON}" app/gen_topology.py --config "${config}" --out "${topology}"; generated+=("${topology}")
  done
  "${PYTHON}" app/k5_exp10_tools.py contract "${generated[@]}"
done
TOPOLOGY_BACKUP="${RESULT_ROOT}/raw/helm_topology_before.json"; cp helm/ahbn/topology.json "${TOPOLOGY_BACKUP}"
restore_topology(){ cp "${TOPOLOGY_BACKUP}" helm/ahbn/topology.json; }; trap restore_topology EXIT
for seed in "${seeds[@]}"; do
  for algorithm in "${algorithms[@]}"; do
    CURRENT_STAGE="GKE run"; CURRENT_SEED="${seed}"; CURRENT_TREATMENT="${algorithm}"
    run_dir="${RESULT_ROOT}/runs/seed${seed}/${algorithm}"; config="${RESULT_ROOT}/configs/${algorithm}_seed${seed}.yaml"
    case "${config}" in "${ROOT_DIR}"/*) relative_config="${config#${ROOT_DIR}/}";; *) fail "RESULT_ROOT must be inside project root";; esac
    OUTDIR="${run_dir}" NAMESPACE="${NAMESPACE}" RELEASE="${RELEASE}" IMAGE="${IMAGE}" PYTHON="${PYTHON}" SKIP_PLOT=1 CAPTURE_STREAM=1 POD_MANAGEMENT_POLICY=Parallel scripts/run_experiment.sh "${relative_config}"
    cp "${RESULT_ROOT}/generated/${algorithm}_seed${seed}.json" "${run_dir}/topology_role_mapping.json"
    "${PYTHON}" app/k5_exp10_tools.py run --run-dir "${run_dir}"
    grep '"event": "dcsoc_maintenance"' "${run_dir}/logs.jsonl" >"${run_dir}/dcsoc_maintenance_trace.jsonl" || true
    grep -E '"event": "(ahbn_controller_trace|k5_final_actuator_decision)"' "${run_dir}/logs.jsonl" >"${run_dir}/ahbn_adaptive_trace.jsonl" || true
  done
done
CURRENT_STAGE="analysis"; "${PYTHON}" scripts/k5_exp10_analysis.py --root "${RESULT_ROOT}" --mode "${MODE}"
shasum -a 256 app/ahbn_controller.py app/peer.py >"${RESULT_ROOT}/canonical_hashes_after.txt"; cmp "${RESULT_ROOT}/canonical_hashes_before.txt" "${RESULT_ROOT}/canonical_hashes_after.txt"
trap - EXIT; restore_topology; trap - ERR; echo "K5 Exp10 ${MODE} complete: ${RESULT_ROOT}"
