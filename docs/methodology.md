# Methodology

How to get a trustworthy answer from `bench`, and what the harness does (and does not) guarantee.

## What is being measured

"Token savings" can mean several different quantities. Do not mix them:

| Layer | Quantity | Suitable headline? |
|---|---|---|
| Command process | Raw stdout/stderr bytes | No, this is only the filter's input |
| Tool boundary | Text the agent actually receives | Diagnostic only |
| Model request | Uncached / cache-created input tokens | Mechanism metric |
| Whole task | All input, cached input, output and reasoning tokens | Yes |
| Economics | Cost per attempt | Yes, with quality beside it |
| Outcome | Cost per successful task | Best decision metric |

An optimizer can compress a command's output by 90% and still save nothing end to end when the agent
mostly uses built-in file/search tools instead of Bash, the harness already truncates long tool
results, the compressed text causes a re-read or an extra turn, cached input dominates the bill, or
the task fails more often. So `bench` measures the whole task with the agent's own usage records and
grades correctness next to it. Optimizer self-reports (`rtk gain`) are kept as diagnostics only: they
prove the tool ran, not that the bill went down.

## How a trial is kept fair

| Guarantee | How |
|---|---|
| No state leaks between trials | Every trial gets a fresh sandbox, removed afterwards. Sandboxes persist packages, caches and agent history across restarts, so reuse would contaminate results |
| Agent cannot see the real fix | Snapshot is `git archive <commit>` re-inited as one commit, or the last `history` commits. No later history, no remote |
| Arms differ only in tools | Same template image, task, model, effort, limits and `setup:` for every arm. Tools are installed per trial from `tools/<name>/setup.sh` |
| Install time does not skew timing | `setup_s` (task setup + tool install) is recorded separately from agent `wall_s` |
| No order / time-of-day bias | `bench run` shuffles arms × reps × tasks into one plan |
| Failures stay visible | A trial that dies before grading still writes `meta.json` with `error` and shows as `ERR` in the report |
| Committed work is captured | `patch.diff` is taken against the `bench-base` tag, not `HEAD` |
| Usage is first-hand | Tokens and cost come from claude `stream-json` / codex `exec --json`, not from the optimizer |

## Designing tasks

A good task has:

- a pinned repo and commit;
- one unambiguous prompt;
- a deterministic `grade` command (exit 0 = pass);
- known wall-time and resource limits;
- no network need unless that is what you test.

Use real tasks from real repositories, not only synthetic noisy-output fixtures. Fixtures show an
optimizer's best case; real work shows whether it helps.

Spread tasks over exposure strata, so a result is not an artifact of one kind of work:

- shell / test / build heavy;
- source navigation;
- mixed implementation and debugging;
- low-output negative control, where the optimizer should change nothing.

## Running an experiment

1. **Wiring check.** One rep per arm on a few tasks. Look into the artifacts: right model and effort
   ran, treatment was active (`claude-settings.json`, `rtk-gain.txt`), control shows no trace of it,
   usage and session logs were captured, grader result makes sense.
2. **Variance pilot.** At least 3 reps per arm. Agent behavior varies enough that a single pair of
   runs is not evidence. `10 tasks × 2 arms × 3 reps = 60 trials` per agent is a reasonable start.
3. **Confirmatory run.** Size it from the pilot variance. Write down hypotheses, endpoints, stopping
   rules and failure policy first; see the [experiment template](experiment-template.md).

Rules of thumb:

- Test one optimizer at a time. Combinations are a separate experiment.
- Do not rerun failures silently. Keep them and count them.
- Keep `--jobs 1` when wall time matters.
- Keep the authentication mode identical within a comparison. With subscription/OAuth auth dollars
  are artificial; report tokens instead.

## Analysis

- Unit of analysis is the paired task attempt, not a single command and not the grand total. Totals
  can be dominated by one runaway task.
- Compare within one agent/model/effort. Claude and Codex differ in token accounting, caching and
  tool interfaces, so their raw totals are not comparable. Compare each agent's improvement over its
  own control.
- Report per-task paired deltas, medians and the whole distribution including outliers.
- Primary endpoints: cost (or total tokens) at non-inferior quality, and cost per successful task
  with failed and timed-out trials included.
- Report treatment adoption. RTK on Claude is a hook that rewrites Bash calls mechanically; RTK on
  Codex is instruction-based (`AGENTS.md`), so the agent may simply not use it. That is a property of
  the product, not noise to hide.
- Token fields differ per agent. Codex reports total and cached input, so uncached input is their
  difference. Claude reports uncached input, cache creation and cache reads separately.

`bench report` prints the per-trial table and per-arm medians. Statistics beyond that (bootstrap
intervals, paired tests) are up to you, from the `meta.json` files.

## Confounders to watch

- Agent CLI or model alias changing mid-run. Pin full model ids; rebuild templates deliberately.
- Treatment instructions consuming context in one arm. That is part of the treatment, count it.
- Prompt-cache order effects and provider variance over the day. Shuffling reduces, not removes them.
- Arm names visible to the agent (`OTEL_RESOURCE_ATTRIBUTES` contains the arm). Prefer neutral names
  when that could bias behavior.
- Client-side cost estimates treated as invoices.
- Dropping setup failures or timeouts from only one arm.

## Known limitations of the harness

- `grade` runs inside the trial sandbox after the agent exits. Hidden tests would be reachable by the
  agent, and tools installed by the treatment are still active while grading. Keep graders simple and
  deterministic.
- Network policy is whatever `sbx` is configured with (`allow-all` by default). The snapshot has no
  remote, but the agent can still reach the internet. Tighten with `sbx policy` if needed.
- Templates are referenced by tag, not by digest. `meta.json` records the tag and the `sbx` version.
- Docker injects its own `~/CLAUDE.md` into claude sandboxes. Same in every arm, but the cached
  prefix is larger than in a normal setup.
- No budget cap per trial, only `timeout_min`.

## Prior evidence

The [JetBrains RTK benchmark](https://blog.jetbrains.com/ai/2026/07/rtk-claude-code-token-savings/)
(Claude Code, RTK 0.43.0, 86 tasks, paired runs) found about 20% of tool-result characters reachable
by the hook, a mechanical ceiling of about 3% of input tokens, median cost +7.6% at low effort and
+0.1% at high effort, and unchanged task quality, while RTK self-reported 96.2 million tokens saved.
Its method (free transcript replay, wiring check, repeated pilot, paired full run, independent
grading) is the model for this one. The numbers should not be generalized to other repositories or
to Codex; that is what this harness is for.

## References

- Docker Sandboxes: [overview](https://docs.docker.com/ai/sandboxes/),
  [install](https://docs.docker.com/ai/sandboxes/install/),
  [architecture and persistence](https://docs.docker.com/ai/sandboxes/architecture/),
  [usage](https://docs.docker.com/ai/sandboxes/usage/),
  [templates](https://docs.docker.com/ai/sandboxes/customize/templates/),
  [credentials](https://docs.docker.com/ai/sandboxes/configuration/credentials/)
- [Claude Code headless mode](https://code.claude.com/docs/en/headless) and
  [usage monitoring](https://code.claude.com/docs/en/monitoring-usage)
- [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)
- [RTK](https://github.com/rtk-ai/rtk)
