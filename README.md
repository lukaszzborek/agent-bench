# bench — sandboxed agent benchmark (RTK & friends)

Measures whether a token optimizer (RTK, Serena, graphify, …) really makes a coding agent (Claude Code, Codex)
cheaper on real tasks without breaking correctness. Same task, model and effort; arms differ only in installed tools.

Each trial = fresh Docker Sandbox (microVM) → repo snapshot at pinned commit → optional tool setup → one headless
agent run → artifacts copied out → grader → sandbox removed.

> **Status: work in progress.** Tasks, graders and the collected metrics are still being improved, so results can
> shift between runs and are not always comparable across harness versions. Some graders may fail for reasons
> unrelated to the agent: check `grade.log` before trusting a fail. Most dashboard cells are still n=1, where one
> extra agent turn moves a cell by ±30%. Treat published numbers as exploratory, not as a verdict on any tool.

## Results

Dashboard: <https://lukaszzborek.github.io/agent-bench/>

First full run (2026-09-20, RTK 0.49.0 vs control, Claude Code + `claude-sonnet-5`, 11 tasks, n=1 per arm):
RTK is a wash on cost (−2.3%) with fewer tokens (−13.6%), mostly cheap cache reads. Details and caveats:
[docs/results-2026-09-20-rtk.md](docs/results-2026-09-20-rtk.md).

## Quick start

Requires Docker Sandboxes (`sbx` CLI), Python 3.10+ with PyYAML, git, and Anthropic and/or OpenAI credentials.

```bash
sbx secret set anthropic                         # or /login once in any claude sandbox
sbx secret set openai --oauth                    # Codex via ChatGPT plan
./bench build                                    # bench/claude:v1 and bench/codex:v1
./bench build claude --tag dotnet --deps dotnet  # extra toolchains per template tag

./bench list                                     # tasks, agents, models, arms
./bench run example --arm control                # one trial
./bench run public --reps 3                      # every public task, all arms × 3, shuffled
./bench report                                   # table + per-arm medians over results/
./bench publish                                  # export aggregates to site/data.json (dashboard)
```

## Layout

| path | what |
|---|---|
| `bench` | CLI: `list`, `run`, `report`, `publish`, `judge`, `build` |
| `run_trial.py`, `report.py`, `publish.py`, `judge.py` | trial lifecycle, report, dashboard export, LLM-as-judge |
| `arms.yaml` | shared arms (arm name → tools) |
| `tasks/` | `public/` (22 tasks on public repos), `private/` (git-ignored), `example.yaml` |
| `templates/` | sandbox image `Dockerfile` + toolchain scripts in `deps/` |
| `tools/` | treatments, one `<name>/setup.sh` each: `rtk`, `serena`, `graphify`, `upfront` |
| `site/` | GitHub Pages dashboard |
| `results/` | run output, git-ignored |

## Docs

- [Reference](docs/reference.md) — task file keys, datasets, run flags, artifacts, dashboard, telemetry, caveats,
  tools, adding a tool
- [Methodology](docs/methodology.md) — what is measured, task design, analysis, limitations
- [Experiment preregistration template](docs/experiment-template.md)
