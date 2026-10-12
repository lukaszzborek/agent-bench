#!/usr/bin/env bash
# Build pinned templates and load them into sbx.
# Usage: [TAG=v1] [DEPS="dotnet node"] [CLAUDE_VERSION=latest] ./build-templates.sh [claude|codex ...]
# DEPS = space-separated scripts from templates/deps/<name>.sh, baked as root. Empty = plain base.
# CLAUDE_VERSION = Claude Code to install over the base image's: latest (default), stable or x.y.z.
set -euo pipefail
cd "$(dirname "$0")"
TAG="${TAG:-v1}"
DEPS="${DEPS:-}"
CLAUDE_VERSION="${CLAUDE_VERSION:-latest}"
declare -A BASE=([claude]=docker/sandbox-templates:claude-code [codex]=docker/sandbox-templates:codex)
[ $# -eq 0 ] && set -- claude codex
for agent in "$@"; do
  img="bench/${agent}:${TAG}"
  docker build --pull -t "$img" --build-arg "BASE=${BASE[$agent]}" --build-arg "DEPS=${DEPS}" \
    --build-arg "CLAUDE_VERSION=${CLAUDE_VERSION}" templates
  tar="/tmp/bench-${agent}-${TAG}.tar"
  docker image save "$img" -o "$tar"
  sbx template load "$tar"
  rm -f "$tar"
  echo "loaded template $img (deps: ${DEPS:-none})"
done
sbx template ls
