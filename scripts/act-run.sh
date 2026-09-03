#!/usr/bin/env bash
# Local act convenience wrapper — execution policy lives HERE, not in the YAML.
#
#   scripts/act-run.sh                      # probe only (fast gate)
#   scripts/act-run.sh build                # both triplets, full build (hours)
#   scripts/act-run.sh build linux-x86_64   # single triplet
#
# Logs: append `> /tmp/act.log 2>&1 &` to background it, as usual.
#
# Notes (hard-earned):
#   --pull=false            the image is local; act force-pulls by default and
#                           registry mirrors cannot serve local images
#   --bind                  writes must flow back to the host workspace
#                           (distfiles/stamps/out pooling)
#   --action-offline-mode   actions/ are vendored by act, no re-fetch
set -euo pipefail

MODE="${1:-ci}"
TRIPLET="${2:-linux-x86_64}"
IMAGE="ffmake-act-ubuntu:24.04"

cd "$(dirname "$0")/.."

ARGS=(-P "ubuntu-latest=${IMAGE}" --bind --pull=false --action-offline-mode)

case "$MODE" in
  ci)
    exec gh act workflow_dispatch -W .github/workflows/ci.yml "${ARGS[@]}" ;;
  build)
    exec gh act workflow_dispatch -W .github/workflows/build.yml "${ARGS[@]}" \
      --input full=true --input "triplets=${TRIPLET}" ;;
  *)
    echo "usage: $0 [ci|build] [triplet]" >&2; exit 2 ;;
esac
