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

HERE = Path(__file__).resolve().parent


def task_datasets() -> dict[str, str]:
    """task id -> dataset, for results written before meta.json recorded the dataset."""
    tasks = HERE / "tasks"
    return {yaml.safe_load(p.read_text())["id"]: p.parent.name if p.parent != tasks else "-"
            for p in tasks.rglob("*.yaml")}


def usage(agent: str, u: dict) -> dict:
    """Token fields normalized across agents: codex counts cached input inside input_tokens."""
    if agent == "codex":
        cached = u.get("cached_input_tokens") or 0
        return {"in": (u.get("input_tokens") or 0) - cached, "cache_read": cached, "cache_write": 0,
                "out": u.get("output_tokens") or 0}
    return {"in": u.get("input_tokens") or 0, "cache_read": u.get("cache_read_input_tokens") or 0,
            "cache_write": u.get("cache_creation_input_tokens") or 0, "out": u.get("output_tokens") or 0}


def row(m: dict, run: str, datasets: dict[str, str]) -> dict:
    t, s = m["task"], m.get("summary") or {}
    dataset = t.get("dataset") or datasets.get(t["id"], "private")
    task = t["id"]
    if dataset != "public":
        task = f"{dataset}-{hashlib.sha1(t['id'].encode()).hexdigest()[:6]}"
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
        "sbx": (m.get("sbx_version") or "").removeprefix("sbx version: ").split(" ")[0],
    }


def publish(roots: list[Path], out: Path):
    """Merge every meta.json under `roots` (results/ or run dirs) into `out`."""
    datasets = task_datasets()
    data = json.loads(out.read_text()) if out.exists() else {"trials": []}
    rows = {r["trial"]: r for r in data["trials"]}
    added = 0
    for root in roots:
        for p in (*root.glob("*/meta.json"), *root.glob("*/*/meta.json")):
            r = row(json.loads(p.read_text()), p.parent.parent.name, datasets)
            added += r["trial"] not in rows
            rows[r["trial"]] = r
    data = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "trials": sorted(rows.values(), key=lambda r: (r["started"] or "", r["trial"]))}
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(data, indent=1) + "\n")
    print(f"{out}: {len(rows)} trials ({added} new)")
