#!/usr/bin/env bash
# Build the CI image. Local builds need the host proxy at build time — it is
# passed explicitly, never defaulted (GitHub builds run proxy-free).
#   scripts/build-image.sh                    # local: proxy default below
#   TAG=ffmake-act-ubuntu:24.04-20260903 scripts/build-image.sh
set -euo pipefail

TAG="${TAG:-ffmake-act-ubuntu:24.04}"
PROXY="${XRAY_PROXY:-http://127.0.0.1:10808}"

cd "$(dirname "$0")/.."
docker build --network host \
  --build-arg XRAY_PROXY="$PROXY" \
  -f docker/Dockerfile -t "$TAG" docker
echo "built $TAG"
