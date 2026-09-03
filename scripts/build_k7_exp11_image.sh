#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "${ROOT_DIR}"
IMAGE="${IMAGE:-wwiras/ahbn2-peer:k7-exp11-frozen-s5-20260903-amd64}"
docker buildx build --platform linux/amd64 --load -f app/Dockerfile.k7_exp11 -t "${IMAGE}" app
docker push "${IMAGE}"
echo "Pushed ${IMAGE}"
