"""Merge meta.json files into site/data.json, the data of the GitHub Pages dashboard. Driven by `bench publish`.

data.json is the durable store: rows are keyed by trial and merged, so wiping results/ loses nothing already
published. Only aggregates leave the machine: no prompts, patches, logs or error text. Tasks outside the `public`
dataset are published under a stable alias (`<dataset>-<hash>`), because their ids name private repos.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from run_trial import graphify_stats, rtk_stats, summarize

HERE = Path(__file__).resolve().parent


def task_info() -> dict[str, tuple[str, list[str]]]:
    """task id -> (dataset, tags) from the task files as they are now, so retagging also applies to old trials
    and results written before meta.json recorded the dataset still get one."""
    tasks = HERE / "tasks"
    info = {}
    for p in tasks.rglob("*.yaml"):
        t = yaml.safe_load(p.read_text())
        info[t["id"]] = (p.parent.name if p.parent != tasks else "-", t.get("tags") or [])
    return info


def usage(agent: str, u: dict) -> dict:
    """Token fields normalized across agents: codex counts cached input inside input_tokens."""
    if agent == "codex":
        cached = u.get("cached_input_tokens") or 0
        return {"in": (u.get("input_tokens") or 0) - cached, "cache_read": cached, "cache_write": 0,
                "out": u.get("output_tokens") or 0}
    return {"in": u.get("input_tokens") or 0, "cache_read": u.get("cache_read_input_tokens") or 0,
            "cache_write": u.get("cache_creation_input_tokens") or 0, "out": u.get("output_tokens") or 0}


def published_name(task_id: str, dataset: str) -> str:
    return task_id if dataset == "public" else f"{dataset}-{hashlib.sha1(task_id.encode()).hexdigest()[:6]}"


def row(m: dict, run: str, info: dict[str, tuple[str, list[str]]], trial_dir: Path) -> dict:
    t = m["task"]
    # re-derived from the raw logs when they are still around, so trials recorded before a stat existed get it too
    jsonl = trial_dir / "agent.jsonl"
    s = summarize(t["agent"], jsonl) if jsonl.exists() else m.get("summary") or {}
    rtk = rtk_stats(trial_dir / "rtk-data") or m.get("rtk") or {}
    graphify = graphify_stats(trial_dir, (m.get("tool_logs") or {}).get("graphify")) or m.get("graphify") or {}
    dataset = t.get("dataset") or info.get(t["id"], ("private",))[0]
    task = published_name(t["id"], dataset)
    tokens = usage(t["agent"], s.get("usage") or {})
    status = "error" if m.get("error") else "pass" if m.get("grade_exit") == 0 else "fail"
    return {
        "trial": m["trial"].replace(t["id"], task), "run": run.replace(t["id"], task), "started": m.get("started"),
        "dataset": dataset, "task": task, "agent": t["agent"], "model": t["model"], "effort": t.get("effort"),
        "arm": m["arm"], "tools": m.get("tools") or [], "rep": m.get("rep"), "status": status,
        "timeout": m.get("agent_exit") == "timeout", "wall_s": m.get("wall_s"), "setup_s": m.get("setup_s"),
        "turns": s.get("num_turns"), "cost": s.get("total_cost_usd") and round(s["total_cost_usd"], 4),
        **tokens, "tokens": sum(tokens.values()),
        "patch_lines": m.get("patch_lines"), "template": m.get("template"), "versions": m.get("versions") or {},
        "tool_calls": s.get("tool_calls") or {},
        "ctx_first": s.get("ctx_first"), "ctx_peak": s.get("ctx_peak"), "ctx_turns": s.get("ctx_turns") or [],
        "tool_out": s.get("tool_out"), "tool_out_by": s.get("tool_out_by") or {},
        "rtk": rtk, "rtk_saved": rtk.get("saved"), "graphify": graphify,
        "sbx": (m.get("sbx_version") or "").removeprefix("sbx version: ").split(" ")[0],
    }


def publish(roots: list[Path], out: Path):
    """Merge every meta.json under `roots` (results/ or run dirs) into `out`."""
    info = task_info()
    data = json.loads(out.read_text()) if out.exists() else {"trials": []}
    rows = {r["trial"]: r for r in data["trials"]}
    added = 0
    for root in roots:
        for p in (*root.glob("*/meta.json"), *root.glob("*/*/meta.json")):
            r = row(json.loads(p.read_text()), p.parent.parent.name, info, p.parent)
            added += r["trial"] not in rows
            rows[r["trial"]] = r
    # every row, not just the merged ones: trials whose logs are gone still follow the current tags
    tags = {published_name(i, d): t for i, (d, t) in info.items()}
    for r in rows.values():
        r["tags"] = tags.get(r["task"], [])
    data = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "trials": sorted(rows.values(), key=lambda r: (r["started"] or "", r["trial"]))}
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(data, indent=1) + "\n")
    print(f"{out}: {len(rows)} trials ({added} new)")
