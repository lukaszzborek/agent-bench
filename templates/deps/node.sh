#!/usr/bin/env bash
# Node LTS from NodeSource. Pin major here.
set -euo pipefail
MAJOR="${NODE_MAJOR:-22}"
apt-get update
apt-get install -y --no-install-recommends curl ca-certificates
curl -fsSL "https://deb.nodesource.com/setup_${MAJOR}.x" | bash -
apt-get install -y --no-install-recommends nodejs
rm -rf /var/lib/apt/lists/*
node --version && npm --version
