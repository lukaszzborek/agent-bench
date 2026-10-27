#!/usr/bin/env python3
"""One benchmark trial: fresh sbx sandbox -> repo snapshot -> optional treatment -> agent run -> artifacts -> grade -> rm.

Driven by `bench run`. Results: <run_dir>/<arm>-r<rep>/
"""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SBX_HOME = "/home/agent"


def sh(*cmd, check=True, input=None, timeout=None, capture=True):
    r = subprocess.run(cmd, input=input, text=True, timeout=timeout,
                       stdout=subprocess.PIPE if capture else None,
                       stderr=subprocess.PIPE if capture else None)
    if check and r.returncode != 0:
        sys.exit(f"FAILED ({r.returncode}): {' '.join(cmd)}\n{r.stderr}")
    return r


def sbx_exec(name, *cmd, workdir=None, input=None, timeout=None, check=True):
    args = ["sbx", "exec"]
    if input is not None:
        args.append("-i")
    if workdir:
        args += ["-w", workdir]
    return sh(*args, name, *cmd, input=input, timeout=timeout, check=check)


def make_snapshot(repo: str, commit: str, dest: Path, history: int = 0) -> str:
    """Export tree at `commit` into a fresh repo so the agent cannot see later history.

    `history` = number of real commits ending at `commit` to keep (shallow fetch); 0 = one synthetic commit.
    The base is tagged `bench-base` so the patch can be taken against it.
    """
    sha = sh("git", "-C", repo, "rev-parse", "--verify", f"{commit}^{{commit}}").stdout.strip()
    dest.mkdir(parents=True)
    env = {**os.environ, "GIT_AUTHOR_NAME": "bench", "GIT_AUTHOR_EMAIL": "bench@local",
           "GIT_COMMITTER_NAME": "bench", "GIT_COMMITTER_EMAIL": "bench@local"}
    init = ["git", "init", "-q", "-b", "main"]
    if history:
        cmds = [init, ["git", "fetch", "-q", "--depth", str(history), str(Path(repo).resolve()), sha],
                ["git", "reset", "-q", "--hard", "FETCH_HEAD"]]
    else:
        tar = subprocess.Popen(["git", "-C", repo, "archive", sha], stdout=subprocess.PIPE)
        subprocess.run(["tar", "-x", "-C", str(dest)], stdin=tar.stdout, check=True)
        tar.wait()
        # -f: the archive holds only tracked files, and the host's global gitignore (not present in the sandbox)
        # must not drop one from the base, or it shows up as a new file in every patch
        cmds = [init, ["git", "add", "-A", "-f"], ["git", "commit", "-q", "-m", f"task base (source {sha[:12]})"]]
    for c in (*cmds, ["git", "tag", "bench-base"]):
        subprocess.run(c, cwd=dest, env=env, check=True, stdout=subprocess.DEVNULL)
    # Reqnroll writes a telemetry id into the repo whenever a .NET build or language server loads a BDD project
    # (mostly Serena's), which would inflate patch_lines for that arm and show the agent an untracked file
    (dest / ".git" / "info").mkdir(exist_ok=True)
    with (dest / ".git" / "info" / "exclude").open("a") as f:
        f.write("**/Reqnroll/userid\n")
    return sha


def agent_cmd(agent: str, task: dict) -> list[str]:
    if agent == "claude":
        return ["claude", "-p", "--output-format", "stream-json", "--verbose",
                "--dangerously-skip-permissions", "--model", task["model"], "--effort", task["effort"]]
    if agent == "codex":
        return ["codex", "exec", "--json", "--dangerously-bypass-approvals-and-sandbox",
                "-m", task["model"], "-c", f'model_reasoning_effort="{task["effort"]}"',
                "-o", f"{SBX_HOME}/last_message.txt", "-"]
    sys.exit(f"unknown agent {agent}")


def version(name: str, binary: str) -> str | None:
    """First line of `<binary> --version` inside the sandbox; None if it fails."""
    r = sbx_exec(name, binary, "--version", check=False)
    return r.stdout.strip().splitlines()[0] if r.returncode == 0 and r.stdout.strip() else None


def install_tools(name: str, agent: str, tools: list[str], work: str, env: dict) -> dict:
    """Copy tools/<tool> into the sandbox and run `setup.sh <agent> <repo dir>` as root with the task's env
    (tool knobs such as SERENA_LANGUAGES). Returns per-tool logs."""
    logs = {}
    if tools:
        sh("sbx", "exec", "-u", "root", name, "mkdir", "-p", "/opt/bench-tools")
    for tool in tools:
        src = HERE / "tools" / tool
        if not (src / "setup.sh").exists():
            sys.exit(f"no setup.sh for tool {tool} in {src}")
        sh("sbx", "cp", str(src), f"{name}:/opt/bench-tools/{tool}")
        env_args = [a for k, v in env.items() for a in ("-e", f"{k}={v}")]
        r = sh("sbx", "exec", "-u", "root", *env_args, name, "bash", f"/opt/bench-tools/{tool}/setup.sh", agent, work)
        logs[tool] = r.stdout + r.stderr
    return logs


def summarize(agent: str, jsonl: Path) -> dict:
    """Pull final usage, per-tool call counts and context stats from the agent's own structured output.

    Cost is roughly requests x context size, so these say why an arm cost more: ctx_first is the fixed prompt +
    tool-definition overhead, ctx_peak how far the context grew, tool_out how much tool output (~tokens, chars/4)
    was fed back."""
    last, calls, seen = None, {}, set()
    ctx, names, tool_out = {}, {}, {}
    for line in jsonl.read_text(errors="replace").splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        # tells "the tool did not help" apart from "the agent never called it"
        if agent == "claude" and ev.get("type") == "assistant":
            msg = ev.get("message") or {}
            # one request streams as several events with the same message id, each repeating its usage
            if msg.get("id") and not ev.get("parent_tool_use_id"):
                u = msg.get("usage") or {}
                ctx[msg["id"]] = sum(u.get(k) or 0 for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            for b in msg.get("content") or []:
                if b.get("type") == "tool_use" and b.get("id") not in seen:
                    seen.add(b.get("id"))
                    names[b["id"]] = b["name"]
                    calls[b["name"]] = calls.get(b["name"], 0) + 1
        elif agent == "claude" and ev.get("type") == "user":
            for b in (ev.get("message") or {}).get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    c = b.get("content")
                    name = names.get(b.get("tool_use_id"), "?")
                    tool_out[name] = tool_out.get(name, 0) + len(c if isinstance(c, str) else json.dumps(c)) // 4
        elif agent == "codex" and ev.get("type") == "item.completed":
            it = ev.get("item") or {}
            name = f"mcp__{it.get('server')}__{it.get('tool')}" if it.get("type") == "mcp_tool_call" else it.get("type")
            if name not in (None, "agent_message", "reasoning"):
                calls[name] = calls.get(name, 0) + 1
        if agent == "claude" and ev.get("type") == "result":
            prev = last
            last = {k: ev.get(k) for k in ("session_id", "num_turns", "duration_ms", "duration_api_ms",
                                            "total_cost_usd", "usage", "modelUsage", "is_error", "subtype")}
            # a background task (Monitor, run_in_background) wakes the agent after its first result, and each
            # result's usage, turns and duration cover only its own segment, while cost and modelUsage are cumulative
            if prev:
                last["usage"] = {**(last["usage"] or {})}
                for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens"):
                    last["usage"][k] = (last["usage"].get(k) or 0) + ((prev.get("usage") or {}).get(k) or 0)
                for k in ("num_turns", "duration_ms"):
                    last[k] = (last.get(k) or 0) + (prev.get(k) or 0)
        elif agent == "codex" and isinstance(ev.get("usage"), dict):
            last = {"usage": ev["usage"], "thread_id": ev.get("thread_id")}
        elif agent == "codex" and ev.get("type") == "thread.started":
            last = {**(last or {}), "thread_id": ev.get("thread_id")}
    if not last:
        return {}
    if ctx:
        sizes = list(ctx.values())
        last |= {"ctx_first": sizes[0], "ctx_peak": max(sizes), "ctx_turns": sizes,
                 "tool_out": sum(tool_out.values()), "tool_out_by": tool_out}
    return {**last, "tool_calls": calls}


def rtk_stats(data: Path) -> dict:
    """What rtk did in a trial, from its own history db (copied out as rtk-data/).

    `rewritten` counts commands the hook routed through rtk; `saved` is rtk's own estimate of tokens it cut."""
    if not (data / "history.db").exists():
        return {}
    with tempfile.TemporaryDirectory() as tmp:
        # copy with the -wal file and open the copy: committed rows may still sit in the WAL, and opening the
        # original would checkpoint into the archived results
        shutil.copytree(data, f"{tmp}/rtk")
        db = sqlite3.connect(f"{tmp}/rtk/history.db")
        try:
            cmds, raw, saved = db.execute(
                "select count(*), coalesce(sum(input_tokens), 0), coalesce(sum(saved_tokens), 0) from commands").fetchone()
            hooks, rewritten = db.execute(
                "select count(*), count(rewritten_cmd) from hook_decisions").fetchone()
        finally:
            db.close()
    return {"cmds": cmds, "raw": raw, "saved": saved, "hooked": hooks, "rewritten": rewritten}


def graphify_stats(trial_dir: Path, setup_log: str | None) -> dict:
    """What graphify offered and what the agent took: graph size from the setup log, queries from graphify's own
    query log (graphify-queries.jsonl), and its PreToolUse hook nudges ("run graphify query first") from the session
    transcript, with how many of them the agent's next tool call actually followed."""
    if not setup_log:
        return {}
    g = re.search(r"Rebuilt: (\d+) nodes, (\d+) edges", setup_log)
    log = trial_dir / "graphify-queries.jsonl"
    queries = [json.loads(line) for line in log.read_text().splitlines() if line.strip()] if log.exists() else []
    kinds = {}
    for q in queries:
        kinds[q.get("kind")] = kinds.get(q.get("kind"), 0) + 1
    nudges = followed = 0
    pending = False
    for f in (trial_dir / "claude-projects").rglob("*.jsonl"):
        if "subagents" in f.parts:
            continue
        for line in f.read_text(errors="replace").splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            a = ev.get("attachment")
            if isinstance(a, dict) and a.get("type") == "hook_additional_context" and "graphify" in json.dumps(a.get("content")):
                nudges += 1
                pending = True
            elif ev.get("type") == "assistant":
                for b in (ev.get("message") or {}).get("content") or []:
                    if b.get("type") == "tool_use":
                        if pending:
                            followed += bool(re.search(r"\bgraphify\s+(query|path|explain)", json.dumps(b.get("input"))))
                        pending = False
    return {"nodes": g and int(g.group(1)), "edges": g and int(g.group(2)), "queries": kinds,
            "query_tok": sum(q.get("result_chars") or 0 for q in queries) // 4, "nudges": nudges, "followed": followed}


def treatment_use(tools: list[str], calls: dict, rtk: dict, graphify: dict) -> dict[str, int]:
    """How often the agent actually used each installed tool that leaves a trace. An arm whose tools were never
    used measures only their overhead (prompt, tool definitions, indexing), not whether they help.
    Tools without a per-use trace (upfront) are left out."""
    use = {}
    if "rtk" in tools:
        use["rtk"] = rtk.get("rewritten") or 0
    if "serena" in tools:
        # initial_instructions only reads Serena's manual; it does no work on the code
        use["serena"] = sum(n for k, n in calls.items()
                            if k.startswith("mcp__serena__") and k != "mcp__serena__initial_instructions")
    if "graphify" in tools:
        use["graphify"] = sum((graphify.get("queries") or {}).values())
    return use


def session_tags(meta: dict) -> list[str]:
    """Tags ai-sessions puts on the trial's sessions (it reads only this key of meta.json)."""
    tags = [f"task:{meta['task']['id']}", f"arm:{meta['arm']}", f"rep:{meta['rep']}"]
    if meta.get("error"):
        tags.append("error")
    elif "grade_exit" in meta:
        tags.append("grade:pass" if meta["grade_exit"] == 0 else "grade:fail")
    if meta.get("agent_exit") == "timeout":
        tags.append("timeout")
    return tags + [f"trial:{meta['trial']}"]


def slug(s: str) -> str:
    """Sandbox/dir-safe form of a name (model ids contain dots)."""
    return re.sub(r"[^a-z0-9-]+", "-", s.lower())


def load_tasks(ref: str) -> list[dict]:
    """Tasks for a ref: a yaml path, a dataset (subdir of tasks/), or a task file name anywhere under tasks/.

    Tasks without an `arms:` block get the shared arms from arms.yaml.
    """
    tasks = HERE / "tasks"
    if Path(ref).is_file():
        paths = [Path(ref)]
    elif (tasks / ref).is_dir():
        paths = sorted((tasks / ref).glob("*.yaml"))
    else:
        paths = sorted(tasks.rglob(f"{ref}.yaml"))
    if not paths:
        names = sorted({p.stem for p in tasks.rglob("*.yaml")} | {p.name for p in tasks.iterdir() if p.is_dir()})
        sys.exit(f"no task or dataset {ref!r}; available: {', '.join(names)}")
    arms = yaml.safe_load((HERE / "arms.yaml").read_text())
    loaded = []
    for p in paths:
        t = yaml.safe_load(p.read_text())
        t.setdefault("arms", arms)
        t["dataset"] = p.parent.name if p.parent != tasks else "-"
        if t.get("hidden"):
            t["hidden"] = str(p.parent / t["hidden"])
        loaded.append(t)
    return loaded


def resolve_repo(repo: str, commit: str) -> str:
    """Local path for a task's `repo`: git URLs are mirrored once into ~/.cache/bench/repos and reused."""
    if "://" not in repo and not repo.startswith("git@"):
        return repo
    dest = Path.home() / ".cache/bench/repos" / Path(repo).name.removesuffix(".git")
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"clone {repo} -> {dest}")
        sh("git", "clone", "-q", "--mirror", repo, str(dest), capture=False)
    elif sh("git", "-C", str(dest), "rev-parse", "-q", "--verify", f"{commit}^{{commit}}", check=False).returncode:
        sh("git", "-C", str(dest), "fetch", "-q")
    return str(dest)


def run_trial(task: dict, arm: str, rep: int, run_dir: Path, template_tag: str, keep: bool):
    agent = task["agent"]
    tools = task["arms"][arm] or []
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = slug(f"{task['id']}-{task['model']}-{arm}-r{rep}")  # model implies agent
    trial = f"{base}-{ts.lower()}"
    if len(trial) > 63:
        # doubles as the sandbox name, which sbx caps at 63; the hash (over the timestamp too) keeps it unique
        trial = f"{base[:54].rstrip('-')}-{hashlib.sha1(trial.encode()).hexdigest()[:8]}"
    out = run_dir / f"{arm}-r{rep}"
    out.mkdir(parents=True)
    work = f"{SBX_HOME}/workspace/{Path(task['repo_path']).name}"
    meta = {"trial": trial, "task": task, "arm": arm, "tools": tools, "rep": rep, "started": ts,
            "template": f"bench/{agent}:{template_tag}"}
    try:
        run_in_sandbox(task, arm, trial, out, work, meta, keep)
    except (SystemExit, subprocess.SubprocessError) as e:
        # keep the failed trial in the report instead of silently dropping it and aborting the remaining reps
        meta["error"] = str(e)
        print(f"[{trial}] ERROR {e}", file=sys.stderr)

    jsonl = out / "agent.jsonl"
    meta["summary"] = summarize(agent, jsonl) if jsonl.exists() else {}
    meta["rtk"] = rtk_stats(out / "rtk-data")
    meta["graphify"] = graphify_stats(out, (meta.get("tool_logs") or {}).get("graphify"))
    meta["tags"] = session_tags(meta)
    (out / "meta.json").write_text(json.dumps(meta, indent=2, default=str))
    s = meta["summary"]
    print(f"[{trial}] done exit={meta.get('agent_exit')} grade={meta.get('grade_exit')} wall={meta.get('wall_s')}s "
          f"cost={s.get('total_cost_usd')} turns={s.get('num_turns')} -> {out}")
    return meta


def run_in_sandbox(task: dict, arm: str, trial: str, out: Path, work: str, meta: dict, keep: bool):
    agent, tools = task["agent"], meta["tools"]
    meta["sbx_version"] = sh("sbx", "version").stdout.strip()
    with tempfile.TemporaryDirectory() as tmp:
        snap = Path(tmp) / "repo"
        meta["source_sha"] = make_snapshot(task["repo_path"], task["commit"], snap, task.get("history", 0))

        env_args = []
        tel = HERE / "telemetry.env"
        if tel.exists():
            env_args += ["--env-file", str(tel)]
        for key, value in (task.get("env") or {}).items():
            env_args += ["-e", f"{key}={value}"]
        env_args += ["-e", f"OTEL_RESOURCE_ATTRIBUTES=trial.id={trial},arm={arm},task={task['id']},agent={agent},model={task['model']}"]
        if agent == "claude":
            # subscription auth would otherwise mount the account's claude.ai connectors (Docs, Gmail, ...) in the trial
            env_args += ["-e", "ENABLE_CLAUDEAI_MCP_SERVERS=false"]
            # -p does not wait for MCP servers by default: the first request (and with it the model's plan) goes out
            # while e.g. Serena is still starting, so its tools are missing exactly when the agent picks its approach
            env_args += ["-e", "MCP_CONNECTION_NONBLOCKING=false"]
            if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
                env_args += ["-e", "CLAUDE_CODE_OAUTH_TOKEN"]  # subscription auth fallback, taken from host env

        print(f"[{trial}] create sandbox")
        sh("sbx", "create", "-q", "--name", trial, "-t", meta["template"],
           "--cpus", str(task.get("cpus", 2)), "--memory", str(task.get("memory", "4g")), *env_args, agent)
        try:
            sh("sbx", "cp", str(snap), f"{trial}:{work}")
            t0 = time.monotonic()
            if task.get("setup"):
                print(f"[{trial}] setup")
                r = sbx_exec(trial, "bash", "-lc", task["setup"], workdir=work, check=False, timeout=1800)
                (out / "setup.log").write_text(r.stdout + r.stderr)
                if r.returncode != 0:
                    sys.exit(f"[{trial}] setup failed ({r.returncode}), see {out / 'setup.log'}")
            meta["tool_logs"] = install_tools(trial, agent, tools, work, task.get("env") or {})
            meta["setup_s"] = round(time.monotonic() - t0, 1)
            # what actually ran: agent CLIs come from a floating base image, tool pins can be overridden via env
            meta["versions"] = {n: version(trial, n) for n in (agent, *tools)}
            # after setup/tools (they download from GitHub), so the agent cannot fetch upstream history or fixes;
            # sandbox-scoped rules are dropped by `sbx rm`
            sh("sbx", "policy", "deny", "network", "--sandbox", trial,
               "github.com,*.github.com,githubusercontent.com,*.githubusercontent.com")
            (out / "prompt.md").write_text(task["prompt"])

            print(f"[{trial}] run {agent}")
            t0 = time.monotonic()
            cmd = agent_cmd(agent, task)
            try:
                r = sbx_exec(trial, *cmd, workdir=work, input=task["prompt"],
                             timeout=task.get("timeout_min", 30) * 60, check=False)
                meta["agent_exit"] = r.returncode
                (out / "agent.jsonl").write_text(r.stdout)
                (out / "agent.stderr").write_text(r.stderr)
            except subprocess.TimeoutExpired as e:
                meta["agent_exit"] = "timeout"
                (out / "agent.jsonl").write_text((e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""))
            meta["wall_s"] = round(time.monotonic() - t0, 1)

            print(f"[{trial}] collect artifacts")
            # diff against the base tag, not HEAD, so work the agent committed is still captured
            patch = sbx_exec(trial, "bash", "-c", "git add -A && git diff --cached bench-base",
                             workdir=work, check=False).stdout
            (out / "patch.diff").write_text(patch)
            meta["patch_lines"] = len(patch.splitlines())
            for src, dst in {
                "claude": [(f"{SBX_HOME}/.claude/projects", "claude-projects"), (f"{SBX_HOME}/.claude/settings.json", "claude-settings.json")],
                "codex": [(f"{SBX_HOME}/.codex/sessions", "codex-sessions"), (f"{SBX_HOME}/.codex", "codex-home")],
            }[agent] + [(f"{SBX_HOME}/.local/share/rtk", "rtk-data"), (f"{SBX_HOME}/.serena/logs", "serena-logs"),
                        (f"{SBX_HOME}/.cache/graphify/queries.jsonl", "graphify-queries.jsonl")]:
                sh("sbx", "cp", f"{trial}:{src}", str(out / dst), check=False)
            if "rtk" in tools:
                (out / "rtk-gain.txt").write_text(sbx_exec(trial, "rtk", "gain", "--history", check=False).stdout)

            if task.get("hidden"):
                # only after the agent exits, so it never sees the grading tests; overwrites its own versions
                sh("sbx", "cp", task["hidden"], f"{trial}:/tmp/bench-hidden")
                sbx_exec(trial, "cp", "-rT", "/tmp/bench-hidden", work)
            if task.get("grade"):
                print(f"[{trial}] grade")
                # xtrace, interleaved with output, names the check that failed: a silent `grep -q` otherwise
                # leaves grade.log empty
                g = sbx_exec(trial, "bash", "-lc", "exec 2>&1; set -x\n" + task["grade"], workdir=work, check=False,
                             timeout=600)
                meta["grade_exit"] = g.returncode
                (out / "grade.log").write_text(g.stdout + g.stderr)
        finally:
            if keep:
                print(f"[{trial}] kept sandbox (sbx rm --force {trial})")
            else:
                sh("sbx", "rm", "--force", trial, check=False)
