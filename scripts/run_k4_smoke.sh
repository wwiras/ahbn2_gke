#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python}"
IMAGE="${IMAGE:-wwiras/ahbn2-peer:v1}"
NAMESPACE="${NAMESPACE:-ahbn-k4-smoke}"
RELEASE="${RELEASE:-ahbn}"
NUM_PEERS=2
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUTDIR="${ROOT_DIR}/outputs/k4_smoke-${TIMESTAMP}"
TOPOLOGY="${OUTDIR}/topology.json"

mkdir -p "${OUTDIR}"

for command_name in kubectl helm; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "ERROR: required command not found: ${command_name}" >&2
    exit 1
  fi
done
if [ ! -x "${PYTHON}" ]; then
  echo "ERROR: Python interpreter is not executable: ${PYTHON}" >&2
  exit 1
fi

collect_artifacts() {
  kubectl -n "${NAMESPACE}" get pods -o wide >"${OUTDIR}/pods.txt" 2>/dev/null || true
  kubectl -n "${NAMESPACE}" get statefulset peer -o wide >"${OUTDIR}/statefulset.txt" 2>/dev/null || true
  kubectl -n "${NAMESPACE}" get services -o wide >"${OUTDIR}/services.txt" 2>/dev/null || true
  kubectl -n "${NAMESPACE}" get endpoints ahbn-peer -o yaml >"${OUTDIR}/endpoints.yaml" 2>/dev/null || true
  kubectl -n "${NAMESPACE}" get events --sort-by=.metadata.creationTimestamp >"${OUTDIR}/events.txt" 2>/dev/null || true
  for peer_id in 0 1; do
    kubectl -n "${NAMESPACE}" logs "peer-${peer_id}" >"${OUTDIR}/peer-${peer_id}.log" 2>/dev/null || true
  done
}
trap collect_artifacts EXIT

printf '%s\n' "${IMAGE}" >"${OUTDIR}/image.txt"
git -C "${ROOT_DIR}" rev-parse HEAD >"${OUTDIR}/git_commit.txt"

echo "[1/9] Verify cluster access"
kubectl cluster-info >/dev/null

echo "[2/9] Generate deterministic topology"
"${PYTHON}" "${ROOT_DIR}/app/gen_topology.py" \
  --config "${ROOT_DIR}/experiments/k4_smoke.yaml" \
  --out "${TOPOLOGY}"
cp "${TOPOLOGY}" "${ROOT_DIR}/helm/ahbn/topology.json"

echo "[3/9] Remove only a previous smoke deployment"
if helm status "${RELEASE}" -n "${NAMESPACE}" >/dev/null 2>&1; then
  helm uninstall "${RELEASE}" -n "${NAMESPACE}" >/dev/null
fi
if kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1; then
  kubectl delete namespace "${NAMESPACE}" --wait=true >/dev/null
fi

echo "[4/9] Install peers with controller disabled"
helm install "${RELEASE}" "${ROOT_DIR}/helm/ahbn" \
  --namespace "${NAMESPACE}" \
  --create-namespace \
  --set namespace="${NAMESPACE}" \
  --set image="${IMAGE}" \
  --set numNodes="${NUM_PEERS}" \
  --set controller.enabled=false

echo "[5/9] Wait for peer readiness"
kubectl -n "${NAMESPACE}" rollout status statefulset/peer --timeout=600s
kubectl -n "${NAMESPACE}" wait --for=condition=ready pod \
  -l app=ahbn-peer --timeout=600s

echo "[6/9] Validate pods and StatefulSet"
pods_json="$(kubectl -n "${NAMESPACE}" get pods -l app=ahbn-peer -o json)"
printf '%s\n' "${pods_json}" >"${OUTDIR}/pods.json"
"${PYTHON}" - "${NUM_PEERS}" "${OUTDIR}/pods.json" <<'PY'
import json, sys
expected = int(sys.argv[1])
with open(sys.argv[2], encoding="utf-8") as stream:
    pods = json.load(stream)["items"]
if len(pods) != expected:
    raise SystemExit(f"ERROR: expected {expected} peer pods, found {len(pods)}")
for pod in pods:
    name = pod["metadata"]["name"]
    if pod.get("status", {}).get("phase") != "Running":
        raise SystemExit(f"ERROR: {name} is not Running")
    statuses = pod.get("status", {}).get("containerStatuses", [])
    if len(statuses) != 1 or not statuses[0].get("ready"):
        raise SystemExit(f"ERROR: {name} container is not Ready")
    if statuses[0].get("restartCount", 0) != 0:
        raise SystemExit(f"ERROR: {name} restart count is not zero")
PY

echo "[7/9] Validate headless service and endpoints"
service_json="$(kubectl -n "${NAMESPACE}" get service ahbn-peer -o json)"
printf '%s\n' "${service_json}" >"${OUTDIR}/service.json"
"${PYTHON}" - "${OUTDIR}/service.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as stream:
    service = json.load(stream)
spec = service["spec"]
if spec.get("clusterIP") != "None":
    raise SystemExit("ERROR: Service/ahbn-peer is not headless")
if not any(int(port.get("port", 0)) == 50051 for port in spec.get("ports", [])):
    raise SystemExit("ERROR: Service/ahbn-peer does not expose port 50051")
PY
endpoints_json="$(kubectl -n "${NAMESPACE}" get endpoints ahbn-peer -o json)"
printf '%s\n' "${endpoints_json}" >"${OUTDIR}/endpoints.json"
"${PYTHON}" - "${NUM_PEERS}" "${OUTDIR}/endpoints.json" <<'PY'
import json, sys
expected = int(sys.argv[1])
with open(sys.argv[2], encoding="utf-8") as stream:
    endpoint = json.load(stream)
addresses = sum((subset.get("addresses", []) for subset in endpoint.get("subsets", [])), [])
if len(addresses) != expected:
    raise SystemExit(f"ERROR: expected {expected} ready endpoints, found {len(addresses)}")
PY
if kubectl -n "${NAMESPACE}" get job ahbn-controller >/dev/null 2>&1; then
  echo "ERROR: Job/ahbn-controller must be absent" >&2
  exit 1
fi

echo "[8/9] Call GetStatus from peer-0 to peer-1"
destination="peer-1.ahbn-peer.${NAMESPACE}.svc.cluster.local:50051"
status_json="$(kubectl -n "${NAMESPACE}" exec -i peer-0 -- python - "${destination}" <<'PY'
import json, sys
import grpc
import peer_pb2
import peer_pb2_grpc
with grpc.insecure_channel(sys.argv[1]) as channel:
    status = peer_pb2_grpc.PeerServiceStub(channel).GetStatus(peer_pb2.Empty(), timeout=10)
print(json.dumps({"ready": status.ready, "alive": status.alive,
                  "peer_id": status.peer_id, "seen_count": status.seen_count}))
PY
)"
printf '%s\n' "${status_json}" >"${OUTDIR}/get_status.json"
"${PYTHON}" - "${OUTDIR}/get_status.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as stream:
    status = json.load(stream)
expected = {"ready": True, "alive": True, "peer_id": 1, "seen_count": 0}
if status != expected:
    raise SystemExit(f"ERROR: unexpected GetStatus response: {status!r}")
PY

echo "[9/9] Verify startup logs and collect evidence"
collect_artifacts
for peer_id in 0 1; do
  if ! grep -q '"event": "grpc_server_started"' "${OUTDIR}/peer-${peer_id}.log"; then
    echo "ERROR: peer-${peer_id} lacks grpc_server_started evidence" >&2
    exit 1
  fi
done

trap - EXIT
echo "============================================================"
echo "K4 SMOKE TEST FINAL STATUS: PASS"
echo "============================================================"
echo "Evidence: ${OUTDIR}"
