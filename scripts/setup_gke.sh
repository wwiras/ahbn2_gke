#!/usr/bin/env bash
set -euo pipefail

CLUSTER="${CLUSTER:-bcgossip-cluster}"
ZONE="${ZONE:-us-central1-a}"
NUM_NODES="${NUM_NODES:-7}"
MACHINE_TYPE="${MACHINE_TYPE:-e2-medium}"

for command_name in gcloud kubectl; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "ERROR: required command not found: ${command_name}" >&2
    exit 1
  fi
done

if gcloud container clusters describe "${CLUSTER}" --zone "${ZONE}" >/dev/null 2>&1; then
  echo "Reusing existing GKE cluster ${CLUSTER} in ${ZONE}."
else
  echo "Creating GKE cluster ${CLUSTER} in ${ZONE}."
  gcloud container clusters create "${CLUSTER}" \
    --zone="${ZONE}" \
    --num-nodes="${NUM_NODES}" \
    --machine-type="${MACHINE_TYPE}" \
    --quiet
fi

gcloud container clusters get-credentials "${CLUSTER}" --zone "${ZONE}"
kubectl cluster-info
kubectl get nodes -o wide

node_json="$(kubectl get nodes -o json)"
python3 -c '
import json, sys
nodes = json.load(sys.stdin)["items"]
if not nodes:
    raise SystemExit("ERROR: cluster has no nodes")
not_ready = []
for node in nodes:
    conditions = node.get("status", {}).get("conditions", [])
    ready = any(c.get("type") == "Ready" and c.get("status") == "True" for c in conditions)
    if not ready:
        not_ready.append(node["metadata"]["name"])
if not_ready:
    raise SystemExit("ERROR: nodes not Ready: " + ", ".join(not_ready))
' <<<"${node_json}"

echo "PASS: GKE cluster ${CLUSTER} is reachable and all nodes are Ready."
