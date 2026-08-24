#!/usr/bin/env bash
set -euo pipefail

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
printf '%s\n' "${K5_ROOT}" >"${K5_ROOT}/result_root.txt"
printf '%s\n' "${IMAGE}" >"${K5_ROOT}/image.txt"

algorithms=(gossip structured dcsoc ahbn)
seeds=(42 43 44 45 46)
factors=(1.0 1.5 2.0 3.0)
if [ "${MODE}" = "smoke" ]; then
  seeds=(42)
  factors=(1.0)
fi

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

if [ "${MODE}" = "formal" ]; then
  "${PYTHON}" "${ROOT_DIR}/app/k5_exp08_tools.py" aggregate "${K5_ROOT}"
fi

echo "K5 ${MODE} execution complete: ${K5_ROOT}"
