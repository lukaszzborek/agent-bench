"""Aggregate meta.json files into one table. Driven by `bench report`."""
import json
from pathlib import Path
from statistics import median

from run_trial import rtk_stats, summarize


def report(roots: list[Path]):
    """Print per-trial table and per-arm medians. Each root is results/ (everything) or one run dir."""
    rows = []
    for p in (p for root in roots for pat in ("*/meta.json", "*/*/meta.json") for p in root.glob(pat)):
        m = json.loads(p.read_text())
        # re-derived like in publish, so trials recorded before a stat existed show it too
        if (p.parent / "agent.jsonl").exists():
            m["summary"] = summarize(m["task"]["agent"], p.parent / "agent.jsonl")
        m["rtk"] = rtk_stats(p.parent / "rtk-data") or m.get("rtk")
        rows.append(m)
    print(f"{'trial':72} {'ok':>3} {'wall_s':>7} {'turns':>5} {'cost$':>8} {'in':>7} {'cache_r':>8} {'cache_w':>8} {'out':>6}")
    groups = {}
    for m in sorted(rows, key=lambda m: m["trial"]):
        s, u = m.get("summary", {}), m.get("summary", {}).get("usage", {}) or {}
        ok = "ERR" if m.get("error") else "y" if m.get("grade_exit") == 0 else "n"
        print(f"{m['trial']:72} {ok:>3} {m.get('wall_s', ''):>7} {s.get('num_turns', ''):>5} "
              f"{(s.get('total_cost_usd') or 0):>8.3f} {u.get('input_tokens', ''):>7} "
              f"{u.get('cache_read_input_tokens', ''):>8} {u.get('cache_creation_input_tokens', ''):>8} {u.get('output_tokens', ''):>6}")
        k = (m["task"]["id"], m["task"]["agent"], m["task"]["model"], m["arm"])
        tokens = sum(u.get(f) or 0 for f in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens"))
        groups.setdefault(k, []).append((m.get("grade_exit") == 0, bool(m.get("error")), s.get("total_cost_usd") or 0,
                                         m.get("wall_s") or 0, tokens, s.get("num_turns") or 0,
                                         s.get("ctx_peak") or 0, s.get("tool_out") or 0, (m.get("rtk") or {}).get("saved") or 0))
    print()
    for (task, agent, model, arm), v in sorted(groups.items()):
        # errored trials are infra failures (sandbox never ran the agent): they say nothing about the arm,
        # so they stay out of n, the pass rate and the medians
        done = [x for x in v if not x[1]]
        n, ok = len(done), sum(1 for x in done if x[0])
        line = f"{task} {agent} {model} {arm:10} n={n} pass={ok}/{n} err={len(v) - n}"
        if done:
            cost, wall, tokens, turns, peak, tool_out, rtk = (median(x[i] for x in done) for i in range(2, 9))
            line += (f" median_cost=${cost:.3f} median_wall={wall:.0f}s median_tokens={tokens:,.0f} median_turns={turns:.0f}"
                     f" peak_ctx={peak:,.0f} tool_out={tool_out:,.0f}" + (f" rtk_saved={rtk:,.0f}" if rtk else ""))
        print(line)
