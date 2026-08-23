#!/usr/bin/env bash
set -euo pipefail

CLUSTER="${CLUSTER:-bcgossip-cluster}"
ZONE="${ZONE:-us-central1-a}"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "ERROR: required command not found: gcloud" >&2
  exit 1
fi

if gcloud container clusters describe "${CLUSTER}" --zone "${ZONE}" >/dev/null 2>&1; then
  echo "Deleting GKE cluster ${CLUSTER} in ${ZONE}."
  gcloud container clusters delete "${CLUSTER}" --zone "${ZONE}" --quiet
  echo "PASS: GKE cluster ${CLUSTER} deleted."
else
  echo "GKE cluster ${CLUSTER} is already absent in ${ZONE}; nothing to delete."
fi
