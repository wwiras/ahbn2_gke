#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python}"
IMAGE="${IMAGE:-wwiras/ahbn2-peer:v1}"
NAMESPACE="${NAMESPACE:-ahbn-k4}"
RELEASE="${RELEASE:-ahbn}"
NUM_PEERS=8
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUTDIR="${ROOT_DIR}/outputs/k4_0_infra-${TIMESTAMP}"
TOPOLOGY="${OUTDIR}/topology.json"
SUMMARY="${OUTDIR}/k4_0_summary.txt"

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
  kubectl get nodes -o wide >"${OUTDIR}/nodes.txt" 2>/dev/null || true
  kubectl -n "${NAMESPACE}" get all -o wide >"${OUTDIR}/deployment_snapshot.txt" 2>/dev/null || true
  kubectl -n "${NAMESPACE}" get pods -o wide >"${OUTDIR}/pods.txt" 2>/dev/null || true
  kubectl -n "${NAMESPACE}" get statefulset peer -o yaml >"${OUTDIR}/statefulset.yaml" 2>/dev/null || true
  kubectl -n "${NAMESPACE}" get services -o wide >"${OUTDIR}/services.txt" 2>/dev/null || true
  kubectl -n "${NAMESPACE}" get endpoints ahbn-peer -o yaml >"${OUTDIR}/endpoints.yaml" 2>/dev/null || true
  kubectl -n "${NAMESPACE}" get events --sort-by=.metadata.creationTimestamp >"${OUTDIR}/events.txt" 2>/dev/null || true
  for peer_id in $(seq 0 7); do
    kubectl -n "${NAMESPACE}" logs "peer-${peer_id}" >"${OUTDIR}/peer-${peer_id}.log" 2>/dev/null || true
  done
}
trap collect_artifacts EXIT

echo "[1/10] Record and check frozen artifact"
git -C "${ROOT_DIR}" rev-parse HEAD >"${OUTDIR}/git_commit.txt"
git -C "${ROOT_DIR}" diff --check
printf '%s\n' "${IMAGE}" >"${OUTDIR}/image.txt"

echo "[2/10] Validate GKE reachability and node readiness"
kubectl cluster-info >/dev/null
nodes_json="$(kubectl get nodes -o json)"
printf '%s\n' "${nodes_json}" >"${OUTDIR}/nodes.json"
"${PYTHON}" - "${OUTDIR}/nodes.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as stream:
    nodes = json.load(stream)["items"]
if not nodes:
    raise SystemExit("ERROR: cluster has no worker nodes")
bad = []
for node in nodes:
    ready = any(c.get("type") == "Ready" and c.get("status") == "True"
                for c in node.get("status", {}).get("conditions", []))
    if not ready:
        bad.append(node["metadata"]["name"])
if bad:
    raise SystemExit("ERROR: nodes not Ready: " + ", ".join(bad))
PY
kubectl get nodes -o wide >"${OUTDIR}/nodes.txt"

echo "[3/10] Generate infrastructure-only topology"
"${PYTHON}" "${ROOT_DIR}/app/gen_topology.py" \
  --config "${ROOT_DIR}/experiments/k4_0_infra.yaml" \
  --out "${TOPOLOGY}"
"${PYTHON}" - "${TOPOLOGY}" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as stream:
    topo = json.load(stream)
checks = [
    (topo["num_nodes"] == 8, "num_nodes must be 8"),
    (topo["topology_type"] == "ba" and topo["ba_m"] == 2, "BA topology must use m=2"),
    (topo["failure"]["mode"] == "none" and topo["failure"]["num_events"] == 0,
     "failure/churn must be inactive"),
    (not topo["bottleneck"]["enabled"] and topo["bottleneck"]["delay_ms"] == 0,
     "bottleneck must be inactive"),
    (topo["workload"]["message_count"] == 0, "workload must be zero"),
]
for passed, message in checks:
    if not passed:
        raise SystemExit("ERROR: " + message)
PY
cp "${TOPOLOGY}" "${ROOT_DIR}/helm/ahbn/topology.json"

echo "[4/10] Remove only a previous K4 infrastructure deployment"
if helm status "${RELEASE}" -n "${NAMESPACE}" >/dev/null 2>&1; then
  helm uninstall "${RELEASE}" -n "${NAMESPACE}" >/dev/null
fi
if kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1; then
  kubectl delete namespace "${NAMESPACE}" --wait=true >/dev/null
fi

echo "[5/10] Install eight peers with controller disabled"
helm install "${RELEASE}" "${ROOT_DIR}/helm/ahbn" \
  --namespace "${NAMESPACE}" \
  --create-namespace \
  --set namespace="${NAMESPACE}" \
  --set image="${IMAGE}" \
  --set numNodes="${NUM_PEERS}" \
  --set controller.enabled=false
kubectl -n "${NAMESPACE}" rollout status statefulset/peer --timeout=600s
kubectl -n "${NAMESPACE}" wait --for=condition=ready pod \
  -l app=ahbn-peer --timeout=600s

echo "[6/10] Validate StatefulSet and peer pods"
statefulset_json="$(kubectl -n "${NAMESPACE}" get statefulset peer -o json)"
printf '%s\n' "${statefulset_json}" >"${OUTDIR}/statefulset.json"
"${PYTHON}" - "${NUM_PEERS}" "${OUTDIR}/statefulset.json" <<'PY'
import json, sys
expected = int(sys.argv[1])
with open(sys.argv[2], encoding="utf-8") as stream:
    sts = json.load(stream)
for field in ("replicas", "currentReplicas", "readyReplicas"):
    value = sts.get("spec" if field == "replicas" else "status", {}).get(field, 0)
    if value != expected:
        raise SystemExit(f"ERROR: StatefulSet {field}={value}, expected {expected}")
PY
pods_json="$(kubectl -n "${NAMESPACE}" get pods -l app=ahbn-peer -o json)"
printf '%s\n' "${pods_json}" >"${OUTDIR}/pods.json"
"${PYTHON}" - "${NUM_PEERS}" "${OUTDIR}/pods.json" <<'PY'
import json, sys
expected = int(sys.argv[1])
with open(sys.argv[2], encoding="utf-8") as stream:
    pods = json.load(stream)["items"]
expected_names = {f"peer-{i}" for i in range(expected)}
names = {pod["metadata"]["name"] for pod in pods}
if names != expected_names:
    raise SystemExit(f"ERROR: peer pod names differ: {sorted(names)}")
for pod in pods:
    name = pod["metadata"]["name"]
    if pod.get("status", {}).get("phase") != "Running":
        raise SystemExit(f"ERROR: {name} is not Running")
    statuses = pod.get("status", {}).get("containerStatuses", [])
    if len(statuses) != 1 or not statuses[0].get("ready"):
        raise SystemExit(f"ERROR: {name} container is not Ready")
    if statuses[0].get("restartCount", 0) != 0:
        raise SystemExit(f"ERROR: {name} has unexpected restarts")
PY

echo "[7/10] Validate Service and endpoints"
service_json="$(kubectl -n "${NAMESPACE}" get service ahbn-peer -o json)"
printf '%s\n' "${service_json}" >"${OUTDIR}/service.json"
"${PYTHON}" - "${OUTDIR}/service.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as stream:
    spec = json.load(stream)["spec"]
if spec.get("clusterIP") != "None":
    raise SystemExit("ERROR: Service/ahbn-peer is not headless")
if not any(int(port.get("port", 0)) == 50051 for port in spec.get("ports", [])):
    raise SystemExit("ERROR: gRPC port 50051 is absent")
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
    raise SystemExit(f"ERROR: ready endpoints={len(addresses)}, expected {expected}")
PY

echo "[8/10] Call GetStatus on every peer from peer-0"
statuses_file="${OUTDIR}/get_status.jsonl"
: >"${statuses_file}"
for peer_id in $(seq 0 7); do
  destination="peer-${peer_id}.ahbn-peer.${NAMESPACE}.svc.cluster.local:50051"
  kubectl -n "${NAMESPACE}" exec -i peer-0 -- python - "${destination}" "${peer_id}" <<'PY' >>"${statuses_file}"
import json, sys
import grpc
import peer_pb2
import peer_pb2_grpc
with grpc.insecure_channel(sys.argv[1]) as channel:
    status = peer_pb2_grpc.PeerServiceStub(channel).GetStatus(peer_pb2.Empty(), timeout=10)
print(json.dumps({"expected_peer_id": int(sys.argv[2]), "ready": status.ready,
                  "alive": status.alive, "peer_id": status.peer_id,
                  "seen_count": status.seen_count}))
PY
done
"${PYTHON}" - "${statuses_file}" "${NUM_PEERS}" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as stream:
    statuses = [json.loads(line) for line in stream if line.strip()]
expected = int(sys.argv[2])
if len(statuses) != expected:
    raise SystemExit(f"ERROR: GetStatus responses={len(statuses)}, expected {expected}")
for status in statuses:
    if not status["ready"] or not status["alive"]:
        raise SystemExit(f"ERROR: peer not healthy: {status}")
    if status["peer_id"] != status["expected_peer_id"]:
        raise SystemExit(f"ERROR: peer_id mismatch: {status}")
if sum(status["seen_count"] for status in statuses) != 0:
    raise SystemExit("ERROR: seen_count total is nonzero; dissemination may have started")
PY
if kubectl -n "${NAMESPACE}" get job ahbn-controller >/dev/null 2>&1; then
  echo "ERROR: Job/ahbn-controller must be absent" >&2
  exit 1
fi

echo "[9/10] Verify logs and capture runtime evidence"
collect_artifacts
: >"${OUTDIR}/fatal_scan.txt"
for peer_id in $(seq 0 7); do
  log_file="${OUTDIR}/peer-${peer_id}.log"
  if ! grep -q '"event": "grpc_server_started"' "${log_file}"; then
    echo "ERROR: peer-${peer_id} lacks grpc_server_started evidence" >&2
    exit 1
  fi
  if grep -Ein 'Traceback \(most recent call last\)|(^|[^a-z])FATAL([^a-z]|$)|segmentation fault|unhandled exception' "${log_file}" >>"${OUTDIR}/fatal_scan.txt"; then
    echo "ERROR: obvious fatal runtime condition found in peer-${peer_id}.log" >&2
    exit 1
  fi
done

echo "[10/10] Write K4.0 gate summary"
cat >"${SUMMARY}" <<EOF
K4.0 — KUBERNETES INFRASTRUCTURE HEALTH

GKE cluster reachable                PASS
Kubernetes nodes Ready               PASS

StatefulSet/peer                     PASS
Expected peer replicas               8
Ready peer replicas                  8/8

Peer pods Running                    8/8
Peer containers Ready                8/8
Unexpected restarts                  0

Headless Service/ahbn-peer           PASS
gRPC port 50051                      PASS
Peer endpoints                       8/8

Peer-to-peer GetStatus               PASS
ready=true                           8/8
alive=true                           8/8
peer_id correct                      8/8

ahbn-controller Job                  ABSENT
Failure injection                    INACTIVE
Bottleneck                           INACTIVE
Churn                                INACTIVE
Dissemination                        NOT STARTED
seen_count total                     0

K4.0 FINAL STATUS: PASS
EOF

trap - EXIT
cat "${SUMMARY}"
echo "Evidence: ${OUTDIR}"
