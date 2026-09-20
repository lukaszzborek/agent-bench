#!/usr/bin/env bash
# Runs inside sandbox as root. $1 = agent (claude|codex). Installs rtk and activates it for the agent user.
set -euo pipefail
agent="$1"
RTK_VERSION="${RTK_VERSION:-0.49.0}"
curl -fsSL "https://github.com/rtk-ai/rtk/releases/download/v${RTK_VERSION}/rtk-x86_64-unknown-linux-musl.tar.gz" \
  | tar -xz -C /usr/local/bin && chmod +x /usr/local/bin/rtk
echo "export RTK_TELEMETRY_DISABLED=1" >> /etc/sandbox-persistent.sh
case "$agent" in
  claude) su agent -c "rtk init -g --auto-patch" ;;
  codex)  su agent -c "rtk init -g --codex" ;;
  *) echo "rtk: unsupported agent $agent" >&2; exit 1 ;;
esac
su agent -c "rtk --version && rtk init -g --show"
