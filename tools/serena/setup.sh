#!/usr/bin/env bash
# Runs inside sandbox as root. $1 = agent (claude|codex), $2 = repo workdir.
# Installs Serena (MCP server + hooks), registers it for the agent and pre-indexes the repo so language servers are
# downloaded now (GitHub is blocked after tool setup).
# Optional env SERENA_LANGUAGES (space-separated, e.g. "csharp"): language servers to enable instead of Serena's
# inference, which enables only the most common language (Rust for iggy, which has no toolchain in the image).
set -euo pipefail
agent="$1"
work="$2"
SERENA_VERSION="${SERENA_VERSION:-1.7.0}"
PIN_DATE=2026-09-29T00:00:00Z  # freezes transitive deps too
serena=/usr/local/bin/serena

# su resets PATH; the agent CLIs live in the agent's ~/.local/bin (claude) or npm-global (codex)
as_agent() { su agent -c "PATH=/home/agent/.local/bin:/usr/local/share/npm-global/bin:\$PATH; $1"; }

# system-wide so hooks and the MCP command resolve regardless of the caller's PATH; system python avoids a
# python-build-standalone download
UV_TOOL_DIR=/opt/uv-tools UV_TOOL_BIN_DIR=/usr/local/bin \
  uv tool install -q -p /usr/bin/python3 --exclude-newer "$PIN_DATE" "serena-agent==${SERENA_VERSION}"

# Partial config, Serena fills in defaults. Project data (project.yml, LSP cache, memories) lives in ~/.serena, not in
# the repo, so it never shows up in patch.diff. Headless run: no dashboard/GUI, no "interactive" base mode (tells the
# model to ask the user questions) and no onboarding (would ask the user, or spend tokens writing memories).
as_agent 'mkdir -p ~/.serena && cat > ~/.serena/serena_config.yml' <<'YAML'
web_dashboard: false
web_dashboard_open_on_launch: false
gui_log_window: false
project_serena_folder_location: "/home/agent/.serena/projects/$projectFolderName"
base_modes:
  - editing
default_modes:
  - no-onboarding
projects: []
YAML

lang_args=""
for l in ${SERENA_LANGUAGES:-}; do lang_args+=" --language $l"; done
# A repo can ship its own .serena/project.yml, whose language list wins over --language (e.g. csharp + kotlin in a
# repo run on the node template, which has neither toolchain). Point it at the requested languages; skip-worktree
# keeps the edit out of `git add -A`, so it never shows up in patch.diff.
cfg="$work/.serena/project.yml"
if [ -n "${SERENA_LANGUAGES:-}" ] && [ -f "$cfg" ]; then
  as_agent "python3 - '$cfg' $SERENA_LANGUAGES" <<'PY'
import re, sys
path, langs = sys.argv[1], sys.argv[2:]
block = "language_servers:\n" + "".join(f"- {l}\n" for l in langs)
text = re.sub(r"^language_servers:\n(?:[ \t]*- .*\n)*", block, open(path).read(), flags=re.M)
open(path, "w").write(text)
PY
  as_agent "cd '$work' && git update-index --skip-worktree .serena/project.yml && grep -A3 '^language_servers:' .serena/project.yml"
fi
# inference asks y/N per extra language it detects; answer no so only the main one is enabled
as_agent "cd '$work' && $serena project index '$work'$lang_args --log-level WARNING" < <(yes n)

# Hooks Serena recommends (docs/02-usage/030_clients.md): remind = deny bursts of grep/read in favour of symbolic
# tools, activate = session-start nudge to read Serena's manual. auto-approve is moot under bypass-permissions.
# $1 = settings file (merged, other tools' hooks kept), $2 = serena-hooks --client, $3 = PreToolUse matcher
add_hooks() {
  as_agent "python3 - $1 $2 '$3'" <<'PY'
import json, os, sys
path, client, matcher = os.path.expanduser(sys.argv[1]), sys.argv[2], sys.argv[3]
s = json.load(open(path)) if os.path.exists(path) else {}
hooks = s.setdefault("hooks", {})
for event, m, cmd in [("PreToolUse", matcher, "remind"), ("SessionStart", "", "activate"), ("SessionEnd", "", "cleanup")]:
    hooks.setdefault(event, []).append(
        {"matcher": m, "hooks": [{"type": "command", "command": f"/usr/local/bin/serena-hooks {cmd} --client={client}"}]})
os.makedirs(os.path.dirname(path), exist_ok=True)
json.dump(s, open(path, "w"), indent=2)
PY
}

case "$agent" in
  claude)
    as_agent "claude mcp add --scope user serena -- $serena start-mcp-server --context claude-code --project '$work'"
    add_hooks '~/.claude/settings.json' claude-code ""
    ;;
  codex)
    as_agent 'mkdir -p ~/.codex && cat >> ~/.codex/config.toml' <<TOML

[mcp_servers.serena]
command = "$serena"
args = ["start-mcp-server", "--context=codex", "--project", "$work"]
startup_timeout_sec = 60
tool_timeout_sec = 300
TOML
    add_hooks '~/.codex/hooks.json' codex Bash
    ;;
  *) echo "serena: unsupported agent $agent" >&2; exit 1 ;;
esac
as_agent "$serena --version && $agent mcp get serena && ls ~/.serena/language_servers/static"
