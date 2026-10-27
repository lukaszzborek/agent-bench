"""LLM-as-judge over finished trials: checks each patch.diff against the task prompt with `claude -p`. Driven by
`bench judge`.

The grader decides correctness; the judge answers yes/no checks the tests cannot see (requested tests and docs,
scope, weakened assertions). Checks are pass/fail rather than scores, and each trial is judged `votes` times with a
per-check majority, because one 1-5 score from one call moved by a full point between identical calls.

Runs on the host after the trials, so old results can be judged again with new checks. The judge sees only the
prompt, the diff and the grader outcome, never the arm or its tools. Read-only tasks are skipped: their ANSWER.txt
grader is exact. Writes judge.json next to meta.json.
"""
import json
import subprocess
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent

# Asked for every `coding` task; a task's `judge:` list adds its own checks after these.
DEFAULT_CHECKS = [
    "tests: the diff adds or updates tests that exercise the changed behaviour, beyond the happy path",
    "kept-tests: no existing test or assertion is deleted, skipped or weakened, except where the task asks for it",
    "scope: no edits unrelated to the task (stray generated files, debug output, drive-by refactors)",
    "complete: every change the task lists explicitly is visibly made in the diff",
]

SCHEMA = {
    "type": "object",
    "properties": {
        "checks": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "pass": {"type": "boolean"}, "evidence": {"type": "string"}},
            "required": ["name", "pass", "evidence"]}},
    },
    "required": ["checks"],
}

MAX_DIFF = 150_000


def task_yamls() -> dict[str, dict]:
    return {t["id"]: t for t in (yaml.safe_load(p.read_text()) for p in (HERE / "tasks").rglob("*.yaml"))}


def judge_prompt(prompt: str, diff: str, passed: bool, checks: list[str]) -> str:
    listed = "\n".join(f"- {c}" for c in checks)
    if len(diff) > MAX_DIFF:
        diff = diff[:MAX_DIFF] + "\n[diff truncated]"
    return f"""You review a patch a coding agent wrote for the task below. A hidden test suite already ran on it and \
{"PASSED" if passed else "FAILED"}; do not re-judge what tests cover, answer only the checks.

Answer every check below with pass true or false, in the order given, using the text before the colon as `name`.
Pass only when the diff shows it; when the diff gives no evidence either way, fail. `evidence` is one sentence citing
the file or hunk. Do not reward length.

Checks:
{listed}

<task>
{prompt}
</task>

<diff>
{diff}
</diff>"""


def ask(prompt: str, model: str) -> dict:
    # no tools and no user/project settings: the judge must not wander the host or pick up a local CLAUDE.md
    out = subprocess.run(["claude", "-p", "--model", model, "--output-format", "json", "--json-schema",
                          json.dumps(SCHEMA), "--tools", "", "--setting-sources", "", "--no-session-persistence"],
                         input=prompt, capture_output=True, text=True, check=True)
    res = json.loads(out.stdout)
    return {"cost": res.get("total_cost_usd") or 0, **res["structured_output"]}


def judge(trial: Path, tasks: dict[str, dict], model: str, votes: int) -> dict | None:
    m = json.loads((trial / "meta.json").read_text())
    task = tasks.get(m["task"]["id"]) or m["task"]
    if m.get("error") or "read-only" in (task.get("tags") or []) or not (trial / "patch.diff").exists():
        return None
    # the defaults are about code and tests; a docs task (STYLEGUIDE.md) is judged on its own checks only
    checks = (DEFAULT_CHECKS if "coding" in (task.get("tags") or []) else []) + (task.get("judge") or [])
    if not checks:
        return None
    p = judge_prompt(m["task"]["prompt"], (trial / "patch.diff").read_text(errors="replace"),
                     m.get("grade_exit") == 0, checks)
    with ThreadPoolExecutor(votes) as ex:
        runs = list(ex.map(lambda _: ask(p, model), range(votes)))
    names = [c.split(":")[0] for c in checks]
    result = []
    for n in names:
        answers = [c for r in runs for c in r["checks"] if c["name"] == n]
        yes = sum(c["pass"] for c in answers)
        # a check a vote left out counts as a fail for that vote
        result.append({"name": n, "pass": yes * 2 > votes, "yes": yes,
                       "evidence": next((c["evidence"] for c in answers if c["pass"] == (yes * 2 > votes)), "")})
    return {"model": model, "votes": votes, "cost": round(sum(r["cost"] for r in runs), 4), "checks": result}


def run(roots: list[Path], model: str, votes: int, force: bool):
    tasks = task_yamls()
    by_arm = defaultdict(lambda: [0, 0])
    for t in sorted({p.parent for root in roots for p in root.rglob("meta.json")}):
        out = t / "judge.json"
        j = json.loads(out.read_text()) if out.exists() and not force else None
        # judge.json from the first proof of concept (1-5 scores, no votes) is redone
        if not j or "votes" not in j:
            j = judge(t, tasks, model, votes)
            if j is None:
                continue
            out.write_text(json.dumps(j, indent=2))
        ok = [c for c in j["checks"] if c["pass"]]
        failed = ",".join(c["name"] for c in j["checks"] if not c["pass"])
        arm = json.loads((t / "meta.json").read_text())["arm"]
        by_arm[arm][0] += len(ok)
        by_arm[arm][1] += len(j["checks"])
        print(f"{t.parent.name[:60]:60} {t.name:18} {len(ok)}/{len(j['checks'])} ${j['cost']:.3f}"
              + (f"  failed: {failed}" if failed else ""))
    print()
    for arm, (ok, n) in sorted(by_arm.items()):
        print(f"{arm:18} checks passed {ok}/{n} ({100 * ok / n:.0f}%)")
