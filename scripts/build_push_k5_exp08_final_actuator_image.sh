#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"
IMAGE="${IMAGE:-wwiras/ahbn2-peer:k5-exp08-final-s5-20260902-tracefix-amd64}"
echo "IMAGE=${IMAGE}"
docker buildx build \
  --platform linux/amd64 \
  -f app/Dockerfile \
  -t "${IMAGE}" \
  --push \
  app
echo "PUSHED IMAGE=${IMAGE}"
echo "NEXT: docker pull --platform linux/amd64 ${IMAGE}"
echo "NEXT: docker image inspect ${IMAGE} --format '{{.Os}}/{{.Architecture}}'"
echo "NEXT: IMAGE=${IMAGE} scripts/run_k5_exp08_smoke.sh"
