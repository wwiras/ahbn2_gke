#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"
PYTHON="${PYTHON:-/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python}"
IMAGE="${IMAGE:-}"
NAMESPACE="${NAMESPACE:-ahbn-k5-h2-ab}"
RELEASE="${RELEASE:-ahbn}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
H2_ROOT="${H2_ROOT:-${ROOT_DIR}/output/k5_h2_selector_ab-${STAMP}}"
RUNS_DIR="${H2_ROOT}/runs"
CONFIG_DIR="${H2_ROOT}/configs"

if [ ! -x "${PYTHON}" ]; then
  echo "ERROR: required Python is not executable: ${PYTHON}" >&2; exit 1
fi
if [ -z "${IMAGE}" ]; then
  echo "ERROR: IMAGE must name the manually built H2 runtime image" >&2; exit 1
fi
for command in kubectl helm; do
  command -v "${command}" >/dev/null 2>&1 || {
    echo "ERROR: required command not found: ${command}" >&2; exit 1;
  }
done

mkdir -p "${RUNS_DIR}" "${CONFIG_DIR}"
exec > >(tee -a "${H2_ROOT}/runner.log") 2>&1
echo "K5 H2 SELECTOR A/B: 5 seeds x 3 reps x 2 treatments = 30 runs"
echo "Only selector treatment differs; overload factor=2.0 delay=1400ms"
printf '%s\n' "${IMAGE}" >"${H2_ROOT}/image.txt"
git rev-parse HEAD >"${H2_ROOT}/git_commit.txt"

TOPOLOGY_BACKUP="${H2_ROOT}/helm_topology_before.json"
cp "${ROOT_DIR}/helm/ahbn/topology.json" "${TOPOLOGY_BACKUP}"
restore_topology() { cp "${TOPOLOGY_BACKUP}" "${ROOT_DIR}/helm/ahbn/topology.json"; }
trap restore_topology EXIT

collect_statuses() {
  local run_dir="$1"
  kubectl -n "${NAMESPACE}" exec -i peer-0 -- python - "${NAMESPACE}" <<'PY' >"${run_dir}/statuses.jsonl"
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

for seed in 42 43 44 45 46; do
  for repetition in 1 2 3; do
    if [ $(((seed + repetition) % 2)) -eq 1 ]; then
      treatments=(selector_control seeded_uniform)
    else
      treatments=(seeded_uniform selector_control)
    fi
    for treatment in "${treatments[@]}"; do
      run_id="k5_h2_seed${seed}_rep${repetition}_${treatment}"
      config="${CONFIG_DIR}/${run_id}.yaml"
      run_dir="${RUNS_DIR}/seed${seed}/rep${repetition}/${treatment}"
      if [ -e "${run_dir}/metrics.json" ]; then
        echo "ERROR: refusing to overwrite completed run ${run_id}" >&2; exit 1
      fi
      "${PYTHON}" "${ROOT_DIR}/scripts/k5_h2_selector_ab_analysis.py" config \
        --base "${ROOT_DIR}/experiments/k5_exp08_ahbn.yaml" --out "${config}" \
        --seed "${seed}" --repetition "${repetition}" --treatment "${treatment}"
      relative_config="${config#${ROOT_DIR}/}"
      echo "=== START ${run_id} ==="
      OUTDIR="${run_dir}" NAMESPACE="${NAMESPACE}" RELEASE="${RELEASE}" \
        IMAGE="${IMAGE}" PYTHON="${PYTHON}" SKIP_PLOT=1 POD_MANAGEMENT_POLICY=Parallel \
        "${ROOT_DIR}/scripts/run_experiment.sh" "${relative_config}"
      collect_statuses "${run_dir}"
      "${PYTHON}" "${ROOT_DIR}/app/k5_exp08_tools.py" run "${run_dir}"
      echo "=== PASS ${run_id} ==="
    done
  done
done

"${PYTHON}" "${ROOT_DIR}/scripts/k5_h2_selector_ab_analysis.py" analyze --root "${H2_ROOT}"
trap - EXIT
restore_topology
echo "K5 H2 selector A/B complete: ${H2_ROOT}"
