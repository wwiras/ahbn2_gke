#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"
IMAGE="${IMAGE:-wwiras/ahbn2-peer:k5-exp10-frozen-s5-matchedsource-20260903-amd64}"
docker buildx build --platform linux/amd64 --load -f app/Dockerfile.k5_final_actuator -t "${IMAGE}" app
docker push "${IMAGE}"
echo "Pushed ${IMAGE}"
