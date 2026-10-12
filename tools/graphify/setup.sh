#!/usr/bin/env bash
# Runs inside sandbox as root. $1 = agent (claude|codex), $2 = repo workdir.
# Installs graphify, builds the code-only knowledge graph of the repo (no LLM/API key) and activates it for the agent.
set -euo pipefail
agent="$1"
work="$2"
GRAPHIFY_VERSION="${GRAPHIFY_VERSION:-0.9.71}"
PIN_DATE=2026-09-29T00:00:00Z  # freezes transitive deps too
graphify=/usr/local/bin/graphify

as_agent() { su agent -c "$1"; }

case "$agent" in
  claude) md=CLAUDE.md; global_md=.claude/CLAUDE.md ;;
  codex)  md=AGENTS.md; global_md=.codex/AGENTS.md ;;
  *) echo "graphify: unsupported agent $agent" >&2; exit 1 ;;
esac

# system-wide so the absolute exe path baked into the hooks is valid for every user
UV_TOOL_DIR=/opt/uv-tools UV_TOOL_BIN_DIR=/usr/local/bin \
  uv tool install -q -p /usr/bin/python3 --exclude-newer "$PIN_DATE" "graphifyy==${GRAPHIFY_VERSION}"
# query log (off by default) records every query/path/explain the agent runs; BASH_ENV makes agent shells source this
echo "export GRAPHIFY_QUERY_LOG=/home/agent/.cache/graphify/queries.jsonl" >> /etc/sandbox-persistent.sh

# The CLI and hooks look for graphify-out/ relative to cwd, so it has to live in the repo root; keep it out of
# `git add -A` (patch.diff) and out of the agent's git status.
as_agent "echo graphify-out/ >> '$work/.git/info/exclude'"
# AST extraction + clustering + GRAPH_REPORT.md; the same command the installed rules tell the agent to run after edits
as_agent "cd '$work' && $graphify update ."

# `graphify <agent> install` writes ./$md (rules) and ./.claude/settings.json | ./.codex/hooks.json (hooks) in cwd.
# Run it in ~ so the hooks land in the agent's user config, then move the rules into the global memory file instead
# of the repo. An existing ~/$md (e.g. the sandbox's own instructions) is set aside so it is not appended to.
as_agent "cd ~ && if [ -e $md ]; then mv $md $md.keep; fi \
  && $graphify $agent install && mkdir -p \$(dirname $global_md) && { echo; cat $md; } >> $global_md && rm $md \
  && if [ -e $md.keep ]; then mv $md.keep $md; fi"

as_agent "$graphify --version; head -12 '$work/graphify-out/GRAPH_REPORT.md'; cat ~/$global_md"
