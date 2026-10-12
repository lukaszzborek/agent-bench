#!/usr/bin/env bash
# Runs inside sandbox as root. $1 = agent (claude|codex), $2 = repo workdir.
# Not a tool of its own: turns off Claude Code's tool search, so MCP tools installed by earlier tools in the arm
# (list it last, e.g. [serena, upfront]) are sent with full schemas on every request instead of as bare names the
# model must load via ToolSearch first. Measures the tool when it is actually in front of the model.
set -euo pipefail
agent="$1"

if [ "$agent" != claude ]; then
  echo "upfront: no tool search to turn off for $agent"
  exit 0
fi

# merged, so hooks other tools wrote to the same file are kept
su agent -c "python3 -" <<'PY'
import json, os
path = os.path.expanduser("~/.claude/settings.json")
s = json.load(open(path)) if os.path.exists(path) else {}
s.setdefault("env", {})["ENABLE_TOOL_SEARCH"] = "false"
os.makedirs(os.path.dirname(path), exist_ok=True)
json.dump(s, open(path, "w"), indent=2)
PY
su agent -c "grep -n ENABLE_TOOL_SEARCH ~/.claude/settings.json"
