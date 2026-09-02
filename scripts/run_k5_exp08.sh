#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python}"
IMAGE="${IMAGE:-}"
NAMESPACE="${NAMESPACE:-ahbn-k5}"
RELEASE="${RELEASE:-ahbn}"
MODE="${1:-formal}"
STAMP="$(date +%Y%m%d_%H%M%S)"
K5_ROOT="${K5_ROOT:-${ROOT_DIR}/outputs/k5_exp08-${STAMP}}"
RUNS_DIR="${K5_ROOT}/runs"
CONFIG_DIR="${K5_ROOT}/configs"

if [ ! -x "${PYTHON}" ]; then
  echo "ERROR: mandated Python is not executable: ${PYTHON}" >&2
  exit 1
fi
if [ -z "${IMAGE}" ]; then
  echo "ERROR: IMAGE must name the image containing the validated K5 source" >&2
  exit 1
fi
if [ "${MODE}" != "formal" ] && [ "${MODE}" != "smoke" ]; then
  echo "Usage: IMAGE=<image> $0 [smoke|formal]" >&2
  exit 1
fi
mkdir -p "${RUNS_DIR}" "${CONFIG_DIR}"
exec > >(tee -a "${K5_ROOT}/terminal.log") 2>&1
echo "COMMAND: IMAGE=${IMAGE} $0 ${MODE}"
printf '%s\n' "${K5_ROOT}" >"${K5_ROOT}/result_root.txt"
printf '%s\n' "${IMAGE}" >"${K5_ROOT}/image.txt"
date -u +%Y-%m-%dT%H:%M:%SZ >"${K5_ROOT}/start_time_utc.txt"
git rev-parse HEAD >"${K5_ROOT}/git_commit.txt"
git status --short >"${K5_ROOT}/git_status.txt"
shasum -a 256 app/ahbn_controller.py app/peer.py >"${K5_ROOT}/canonical_hashes.txt"
shasum -a 256 app/k5_final_actuator_policy.py app/k5_final_actuator_runtime.py >"${K5_ROOT}/final_actuator_hashes.txt"
"${PYTHON}" --version >"${K5_ROOT}/python_version.txt" 2>&1
EXPECTED_CONTROLLER_HASH="dee8cb8e81494bc1448793076803a330602d613e9654ac7fa572d8203f6cc7c8"
EXPECTED_PEER_HASH="64c529f9c32f732c8d4f2c5959c75c0bbed20252328b81b018eb35c6cef10b5a"
EXPECTED_POLICY_HASH="8c7a0658cd226d0349e3ed3c64c943887196fdee57d9ef06874fd8525b683cff"
[ "$(shasum -a 256 app/ahbn_controller.py | awk '{print $1}')" = "${EXPECTED_CONTROLLER_HASH}" ] || { echo "ERROR: canonical controller hash mismatch" >&2; exit 1; }
[ "$(shasum -a 256 app/peer.py | awk '{print $1}')" = "${EXPECTED_PEER_HASH}" ] || { echo "ERROR: canonical peer hash mismatch" >&2; exit 1; }
[ "$(shasum -a 256 app/k5_final_actuator_policy.py | awk '{print $1}')" = "${EXPECTED_POLICY_HASH}" ] || { echo "ERROR: final actuator policy hash mismatch" >&2; exit 1; }

algorithms=(gossip structured dcsoc ahbn)
seeds=(42 43 44 45 46)
factors=(1.0 1.5 2.0 3.0)
if [ "${MODE}" = "smoke" ]; then
  seeds=(42)
  factors=(1.0 3.0)
fi
echo "MATRIX: algorithms=${algorithms[*]} seeds=${seeds[*]} factors=${factors[*]} expected_runs=$((${#algorithms[@]} * ${#seeds[@]} * ${#factors[@]}))"

collect_statuses() {
  local run_dir="$1"
  kubectl -n "${NAMESPACE}" exec -i peer-0 -- python - \
    "${NAMESPACE}" <<'PY' >"${run_dir}/statuses.jsonl"
import json, sys
import grpc
import peer_pb2
import peer_pb2_grpc
namespace = sys.argv[1]
for peer_id in range(20):
    address = f"peer-{peer_id}.ahbn-peer.{namespace}.svc.cluster.local:50051"
    with grpc.insecure_channel(address) as channel:
        status = peer_pb2_grpc.PeerServiceStub(channel).GetStatus(peer_pb2.Empty(), timeout=10)
    print(json.dumps({"expected_peer_id": peer_id, "ready": status.ready,
                      "alive": status.alive, "peer_id": status.peer_id,
                      "seen_count": status.seen_count, "mode": status.mode,
                      "fanout": status.fanout}))
PY
}

for algorithm in "${algorithms[@]}"; do
  echo "=== K5 stage ${algorithm} START ==="
  completed=0
  for seed in "${seeds[@]}"; do
    for factor in "${factors[@]}"; do
      run_id="k5_${algorithm}_seed${seed}_factor${factor}"
      config="${CONFIG_DIR}/${run_id}.yaml"
      run_dir="${RUNS_DIR}/${run_id}"
      if [ -f "${run_dir}/metrics.json" ]; then
        echo "--- REVALIDATE COMPLETED RUN ${run_id} ---"
        "${PYTHON}" "${ROOT_DIR}/app/k5_exp08_tools.py" run "${run_dir}"
        completed=$((completed + 1))
        continue
      fi
      "${PYTHON}" "${ROOT_DIR}/app/k5_exp08_tools.py" config \
        --base "${ROOT_DIR}/experiments/k5_exp08_${algorithm}.yaml" \
        --out "${config}" --algorithm "${algorithm}" --seed "${seed}" --factor "${factor}"
      relative_config="${config#${ROOT_DIR}/}"
      echo "--- RUN ${run_id} ---"
      OUTDIR="${run_dir}" NAMESPACE="${NAMESPACE}" RELEASE="${RELEASE}" \
        IMAGE="${IMAGE}" PYTHON="${PYTHON}" SKIP_PLOT=1 POD_MANAGEMENT_POLICY=Parallel \
        "${ROOT_DIR}/scripts/run_experiment.sh" "${relative_config}"
      collect_statuses "${run_dir}"
      "${PYTHON}" "${ROOT_DIR}/app/k5_exp08_tools.py" run "${run_dir}"
      completed=$((completed + 1))
    done
  done
  echo "=== K5 stage ${algorithm}: ${completed}/${#seeds[@]}x${#factors[@]} PASS ==="
done

"${PYTHON}" "${ROOT_DIR}/app/k5_exp08_tools.py" aggregate "${K5_ROOT}" --mode "${MODE}"
date -u +%Y-%m-%dT%H:%M:%SZ >"${K5_ROOT}/end_time_utc.txt"

echo "K5 ${MODE} execution complete: ${K5_ROOT}"
