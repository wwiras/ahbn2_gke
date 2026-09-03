#!/usr/bin/env bash
set -Eeuo pipefail
CONFIG="$1"; ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; OUTDIR="${OUTDIR:?}"; NAMESPACE="${NAMESPACE:?}"; RELEASE="${RELEASE:-ahbn}"; IMAGE="${IMAGE:?}"; PYTHON="${PYTHON:?}"
mkdir -p "${OUTDIR}"; LOG_FOLLOW_PID=""
collect(){
  if [ -n "${LOG_FOLLOW_PID}" ]; then kill "${LOG_FOLLOW_PID}" 2>/dev/null || true; wait "${LOG_FOLLOW_PID}" 2>/dev/null || true; LOG_FOLLOW_PID=""; fi
  kubectl -n "${NAMESPACE}" get pods -l app=ahbn-peer -o json >"${OUTDIR}/pods.json" 2>/dev/null || true
  kubectl -n "${NAMESPACE}" get events --sort-by=.metadata.creationTimestamp >"${OUTDIR}/pod_readiness_evidence.txt" 2>/dev/null || true
  kubectl -n "${NAMESPACE}" logs job/ahbn-controller >"${OUTDIR}/controller.log" 2>/dev/null || true
  kubectl -n "${NAMESPACE}" logs -l app=ahbn-peer --all-containers=true --max-log-requests=20 --tail=-1 >"${OUTDIR}/final_snapshot.jsonl" 2>/dev/null || true
  { [ -s "${OUTDIR}/peer_stream.jsonl" ] && cat "${OUTDIR}/peer_stream.jsonl"; cat "${OUTDIR}/final_snapshot.jsonl" 2>/dev/null || true; cat "${OUTDIR}/controller.log" 2>/dev/null || true; } >"${OUTDIR}/logs.jsonl"
}
trap collect EXIT
"${PYTHON}" "${ROOT_DIR}/app/k7_gen_topology.py" --config "${ROOT_DIR}/${CONFIG}" --out "${OUTDIR}/topology.json"
cp "${OUTDIR}/topology.json" "${ROOT_DIR}/helm/ahbn/topology.json"; cp "${ROOT_DIR}/${CONFIG}" "${OUTDIR}/generated_config.yaml"
NUM_NODES="$("${PYTHON}" -c 'import json,sys; print(json.load(open(sys.argv[1]))["num_nodes"])' "${OUTDIR}/topology.json")"
helm uninstall "${RELEASE}" -n "${NAMESPACE}" >/dev/null 2>&1 || true
helm install "${RELEASE}" "${ROOT_DIR}/helm/ahbn" --namespace "${NAMESPACE}" --create-namespace --set namespace="${NAMESPACE}" --set image="${IMAGE}" --set numNodes="${NUM_NODES}" --set podManagementPolicy=Parallel --set controller.enabled=false
kubectl -n "${NAMESPACE}" rollout status statefulset/peer --timeout=600s
kubectl -n "${NAMESPACE}" wait --for=condition=ready pod -l app=ahbn-peer --timeout=600s
sleep 5
kubectl -n "${NAMESPACE}" logs -f -l app=ahbn-peer --all-containers=true --max-log-requests=20 --tail=-1 >"${OUTDIR}/peer_stream.jsonl" 2>"${OUTDIR}/peer_stream.err" & LOG_FOLLOW_PID=$!
helm upgrade "${RELEASE}" "${ROOT_DIR}/helm/ahbn" --namespace "${NAMESPACE}" --reuse-values --set controller.enabled=true
kubectl -n "${NAMESPACE}" wait --for=condition=complete job/ahbn-controller --timeout=900s
collect; trap - EXIT
