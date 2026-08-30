#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"
REQUIRED_PYTHON="/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python"
PYTHON="${PYTHON:-${REQUIRED_PYTHON}}"
IMAGE="${IMAGE:-}"
NAMESPACE="${NAMESPACE:-ahbn-k5-final-actuator}"
RELEASE="${RELEASE:-ahbn}"
EXPECTED_CONTEXT="${EXPECTED_CONTEXT:-gke_stoked-cosine-415611_us-central1-a_bcgossip-cluster}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RESUME=0
if [ "${1:-}" = "--resume" ]; then
  [ "$#" -eq 2 ] || { echo "Usage: $0 [--resume RESULT_ROOT]" >&2; exit 2; }
  RESUME=1
  case "$2" in /*) RESULT_ROOT="$2" ;; *) RESULT_ROOT="${ROOT_DIR}/$2" ;; esac
elif [ "$#" -ne 0 ]; then
  echo "Usage: $0 [--resume RESULT_ROOT]" >&2; exit 2
else
  RESULT_ROOT="${RESULT_ROOT:-${ROOT_DIR}/outputs/k5_shortest_actuator_solution_gke/${STAMP}}"
fi
HASH_EXPECTED_CONTROLLER="dee8cb8e81494bc1448793076803a330602d613e9654ac7fa572d8203f6cc7c8"
HASH_EXPECTED_PEER="64c529f9c32f732c8d4f2c5959c75c0bbed20252328b81b018eb35c6cef10b5a"

fail() { echo "ERROR: $*" >&2; exit 1; }
[ -x "${PYTHON}" ] || fail "required Python is not executable: ${PYTHON}"
[ "${PYTHON}" = "${REQUIRED_PYTHON}" ] || fail "Python override forbidden; required: ${REQUIRED_PYTHON}; got: ${PYTHON}"
PYTHON_EXECUTABLE="$("${PYTHON}" -c 'import sys; print(sys.executable)')"
PYTHON_PREFIX="$("${PYTHON}" -c 'import sys; print(sys.prefix)')"
[ "${PYTHON_EXECUTABLE}" = "${REQUIRED_PYTHON}" ] || fail "interpreter identity mismatch: ${PYTHON_EXECUTABLE}"
[ "${PYTHON_PREFIX}" = "/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2" ] || fail "interpreter environment mismatch: ${PYTHON_PREFIX}"
[ -n "${IMAGE}" ] || fail "IMAGE must name the manually built final-actuator image"
for command_name in kubectl helm shasum; do command -v "${command_name}" >/dev/null || fail "missing command: ${command_name}"; done
[ "$(kubectl config current-context)" = "${EXPECTED_CONTEXT}" ] || fail "unexpected kubectl context: $(kubectl config current-context)"
kubectl auth can-i get pods -n "${NAMESPACE}" >/dev/null || fail "GKE authorization/namespace validation failed"

if [ "${RESUME}" -eq 1 ]; then
  [ -d "${RESULT_ROOT}" ] || fail "resume root does not exist: ${RESULT_ROOT}"
  [ -f "${RESULT_ROOT}/image.txt" ] || fail "resume root lacks image provenance: ${RESULT_ROOT}/image.txt"
  [ "$(<"${RESULT_ROOT}/image.txt")" = "${IMAGE}" ] || fail "resume image differs from original image.txt"
fi
mkdir -p "${RESULT_ROOT}"/{raw,logs,runs,results,summary,configs}
exec > >(tee -a "${RESULT_ROOT}/terminal.log") 2>&1
echo "K5 FINAL ACTUATOR GKE: S0 vs S5-C6 only; seeds 42--46; factor 2.0"
echo "Python: ${PYTHON_EXECUTABLE}"
echo "Python version: $("${PYTHON}" --version 2>&1)"
echo "Python prefix: ${PYTHON_PREFIX}"
if [ "${RESUME}" -eq 1 ]; then echo "RESUME ROOT: ${RESULT_ROOT}"; fi
printf '%s\n' "${IMAGE}" >"${RESULT_ROOT}/image.txt"
git rev-parse HEAD >"${RESULT_ROOT}/git_commit.txt"

check_hashes() {
  local controller_hash peer_hash
  controller_hash="$(shasum -a 256 app/ahbn_controller.py | awk '{print $1}')"
  peer_hash="$(shasum -a 256 app/peer.py | awk '{print $1}')"
  [ "${controller_hash}" = "${HASH_EXPECTED_CONTROLLER}" ] || fail "canonical controller hash changed: ${controller_hash}"
  [ "${peer_hash}" = "${HASH_EXPECTED_PEER}" ] || fail "canonical peer hash changed: ${peer_hash}"
  printf '%s  %s\n%s  %s\n' "${controller_hash}" app/ahbn_controller.py "${peer_hash}" app/peer.py
}
check_hashes | tee "${RESULT_ROOT}/canonical_hashes_before.txt"
"${PYTHON}" -m pytest -q tests/test_k5_final_actuator_gke.py

TOPOLOGY_BACKUP="${RESULT_ROOT}/raw/helm_topology_before.json"
cp helm/ahbn/topology.json "${TOPOLOGY_BACKUP}"
restore_topology() { cp "${TOPOLOGY_BACKUP}" helm/ahbn/topology.json; }
trap restore_topology EXIT

for seed in 42 43 44 45 46; do
  if [ $((seed % 2)) -eq 0 ]; then treatments=(S0 S5-C6); else treatments=(S5-C6 S0); fi
  for treatment in "${treatments[@]}"; do
    config="${RESULT_ROOT}/configs/seed${seed}_${treatment}.yaml"
    run_dir="${RESULT_ROOT}/runs/seed${seed}/${treatment}"
    if [ -d "${run_dir}" ]; then
      if [ "${RESUME}" -ne 1 ]; then fail "existing run directory requires --resume: ${run_dir}"; fi
      echo "=== VALIDATE EXISTING seed=${seed} treatment=${treatment} ==="
      "${PYTHON}" scripts/k5_final_actuator_analysis.py validate-run \
        --run-dir "${run_dir}" --seed "${seed}" --treatment "${treatment}"
      echo "=== SKIP VALID COMPLETE RUN seed=${seed} treatment=${treatment} ==="
      continue
    fi
    "${PYTHON}" scripts/k5_final_actuator_analysis.py config \
      --base experiments/k5_exp08_ahbn.yaml --out "${config}" --seed "${seed}" --treatment "${treatment}"
    relative_config="${config#${ROOT_DIR}/}"
    echo "=== START seed=${seed} treatment=${treatment} ==="
    OUTDIR="${run_dir}" NAMESPACE="${NAMESPACE}" RELEASE="${RELEASE}" IMAGE="${IMAGE}" \
      PYTHON="${PYTHON}" SKIP_PLOT=1 POD_MANAGEMENT_POLICY=Parallel \
      scripts/run_experiment.sh "${relative_config}"
    kubectl -n "${NAMESPACE}" get pods -o wide >"${run_dir}/pods_final.txt"
    "${PYTHON}" scripts/k5_final_actuator_analysis.py validate-run \
      --run-dir "${run_dir}" --seed "${seed}" --treatment "${treatment}"
    echo "=== PASS seed=${seed} treatment=${treatment} ==="
  done
done

"${PYTHON}" scripts/k5_final_actuator_analysis.py analyze --root "${RESULT_ROOT}"
check_hashes | tee "${RESULT_ROOT}/canonical_hashes_after.txt"
cmp "${RESULT_ROOT}/canonical_hashes_before.txt" "${RESULT_ROOT}/canonical_hashes_after.txt" || fail "canonical hash records differ"
trap - EXIT
restore_topology
echo "K5 final actuator GKE complete: ${RESULT_ROOT}"
