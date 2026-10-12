# Reference

Details behind the [README](../README.md): build options, task file, datasets, run flags, artifacts, dashboard,
telemetry, caveats and tools.

## Image build

Project toolchains (dotnet, node…) are scripts in `templates/deps/<name>.sh`, baked into the image at build time:

```bash
./bench build claude --tag dotnet --deps dotnet          # bench/claude:dotnet with .NET SDK
./bench build claude --tag rust --deps rust              # bench/claude:rust: Rust 1.98.0 + rust-analyzer (Serena)
./bench run foo --arm control --template-tag dotnet
```

Add a toolchain = add a script (runs as root, pin versions inside). Keep both arms on the same template.

The base image lags behind Claude Code releases, so the build installs Claude Code on top: `CLAUDE_VERSION=latest`
(default), `stable` or an exact `x.y.z`. Auto-update is off in the image (`DISABLE_AUTOUPDATER=1`), so the version
stays fixed for every trial; each trial records it in `meta.json` `versions`. Rebuild every template you compare with
the same exact version: `CLAUDE_VERSION=2.1.296 ./bench build claude --tag dotnet --deps dotnet`.
Per-repo warmup (`dotnet restore`, `npm ci`) belongs in the task's `setup:` key, not the image.

## Task file

`tasks/example.yaml`:

| key | meaning |
|---|---|
| `id` | short slug, becomes part of sandbox/trial name |
| `agent` | `claude` or `codex` |
| `model`, `effort` | pinned per trial, passed on the CLI |
| `template_tag` | image tag from `bench build --tag` (default `v1`); `--template-tag` / `TAG` override |
| `repo`, `commit` | host repo path or git URL + commit. URLs are mirrored once into `~/.cache/bench/repos/<name>` (fetched again only when `commit` is missing), so public tasks run on any machine. Snapshot = `git archive <commit>` re-inited as a single-commit repo, so **no later history, no remote** is visible to the agent |
| `history` | optional N: keep the last N real commits ending at `commit` (shallow fetch, original SHAs) instead of one synthetic commit. For `git log`/`git diff` tasks. The oldest kept commit looks like it adds every file, so scope questions away from it |
| `env` | optional map of environment variables injected into the sandbox for setup, agent commands, and grading; quote values such as `"false"` so YAML keeps them as strings |
| `prompt` | the task, sent on stdin |
| `arms` | optional map arm-name → list of tools; default = shared `arms.yaml`. Each tool = `tools/<name>/setup.sh`, copied in and run as root (`setup.sh <agent> <repo dir>`) before the agent starts. `control: []` = nothing installed |
| `setup` | optional shell run in repo dir after snapshot, before tools/agent (e.g. `dotnet restore`, `npm ci`). Identical for every arm, excluded from agent wall time; non-zero exit aborts trial, log in `setup.log` |
| `hidden` | optional dir (relative to the task yaml) laid over the repo after the agent exits, right before `grade`; same relative paths as in the repo. For grading tests too long to inline in `grade`; overwrites the agent's versions of those files |
| `grade` | shell command run inside the sandbox after the agent exits; exit 0 = pass |
| `timeout_min`, `cpus`, `memory` | limits |

## Datasets

A dataset = subdir of `tasks/`. `tasks/public/` holds tasks on public repos (`repo:` is a git URL, anyone can run
them); `tasks/private/` is git-ignored and holds tasks on repos only you can reach (local path, or a URL your git
credentials can clone).
New dataset = new subdir. A dataset name works anywhere a task name does.

`public/` (22 tasks), grouped by what they exercise:

| kind | tasks | grader |
|---|---|---|
| git history, read-only | `iggy-git-{log,diff,pickaxe}-csharp`, `iggy-git-rename-blame` | `ANSWER.txt` vs known answer |
| code navigation, read-only | `iggy-csharp-callers` (2-level call graph), `iggy-rust-trait-impls` (direct vs blanket impls, `rust` template), `httpx-unraised-exceptions` (Python) | `ANSWER.txt` vs known answer |
| C# fix/feature (iggy SDK, `dotnet` template) | `iggy-utf8-identifier`, `iggy-binarymapper-dos`, `iggy-stats-metrics` (S), `iggy-socket-buffer-default` (M), `iggy-expiry-timespan` (L, 25 files upstream) | hidden xunit test + unit suite |
| Python fix/feature (marshmallow) | `marshmallow-url-fragment`, `marshmallow-schema-validator-data-key`, `marshmallow-enum-none-allow-none` | hidden pytest + full suite |
| Rust fix/feature (`rust` template) | `toml-writer-quote-overflow` (S), `toml-value-datetime-into` (M), `toml-integer-keys` (feature, toml + toml_edit), `iggy-configs-sibling-env` (iggy `core/configs`, ~2 min warm build) | hidden cargo test + crate tests |
| TypeScript fix/feature (remeda) | `remeda-groupby-proto-keys`, `remeda-round-precision`, `remeda-range-step` | hidden vitest + `tsc` |

Code tasks are real upstream fixes pinned at the parent commit; each grader was checked to fail on the pin and pass
with the upstream fix applied, in the same image the trial uses. Upstream fixes are public, so a model may have seen
them in training.

## Run

```bash
./bench list                                       # tasks with dataset, agent, model, template tag, arms
./bench run public --reps 3                        # every task in tasks/public/
./bench run example --arm control                  # one trial; task = dataset, file name under tasks/ or a yaml path
./bench run example --arm rtk --keep               # keep sandbox for inspection
./bench run example --arm control --reps 5         # 5 trials of one arm, then report for this run
./bench run example --reps 3                       # all arms × 3 reps, shuffled, then report
./bench run example iggy-utf8-identifier --reps 3  # several tasks, one shuffled plan
./bench run example --reps 6 --jobs 3              # 3 sandboxes at once
./bench run public --arm control --arm serena      # only these arms (default: every arm of the task)
./bench run public --model claude-opus-5-5         # same tasks, other model (task's agent)
./bench run public --model claude-sonnet-5 --model codex:gpt-5.3-codex --effort high   # one plan per model
./bench report                                     # table + per-arm medians over everything in results/
./bench report results/<run>                       # one run only (several paths allowed)
```

`--jobs` > 1 shares host CPU and API rate limits between trials, so `wall_s` is no longer comparable with
serial runs. Tokens and cost stay valid. Keep `--jobs 1` when timing matters.

`--model [AGENT:]MODEL` is repeatable; each value runs the whole plan with that agent/model, all shuffled together.
Compare arms only within one agent · model · effort. Codex needs its template for the task's tag
(`./bench build codex --tag dotnet --deps dotnet`).

One invocation = one run dir per task and model, one subdir per trial: `results/<task>-<agent>-<model>-<ts>/<arm>-r<rep>/`.
Every trial gets its own sandbox (created, used, removed). A trial that fails before grading still writes
`meta.json` with an `error` field and shows as `ERR` in the report; the remaining trials keep running. Such
infra failures are left out of `n`, the pass rate and the medians, and only counted in `err=`.

## Artifacts (`results/<run>/<arm>-r<rep>/`)

- `agent.jsonl` — claude `stream-json` / codex `exec --json`; final usage + cost parsed into `meta.json`
- `claude-projects/` or `codex-sessions/` — native session history; ai-sessions indexes it directly with a source `{"name": "bench", "path": ".../results", "claude": "**/claude-projects", "codex": "**/codex-sessions", "meta": "meta.json"}` in its config, tagging each session from `tags` in `meta.json` (`compare` tab groups them by arm)
- `patch.diff`, `grade.log`, `prompt.md`, `rtk-gain.txt` + `rtk-data/` (rtk arm), `claude-settings.json` (proves which hooks were active)
- `meta.json` — task, arm, tools, tool setup logs, `setup_s` (install time, separate from `wall_s`), source sha, template, sbx version, `versions` (`--version` of the agent CLI and every installed tool, as run), exit codes, summary

## Dashboard (GitHub Pages)

```bash
./bench publish                     # merge everything in results/ into site/data.json
./bench publish results/<run>       # or only some runs
python3 -m http.server -d site      # preview at http://localhost:8000
git add site/data.json && git commit -m "results: ..." && git push   # workflow deploys site/ to Pages
```

`site/data.json` is the durable store: rows are keyed by trial and merged, so clearing `results/` loses nothing
already published. To drop a bad run, delete its rows (`jq '.trials |= map(select(.run != "<run>"))'`).
Only aggregates are exported (status, tokens, cost, turns, wall, patch size) — no prompts, patches or logs. Tasks
outside the `public` dataset appear as `<dataset>-<hash>` because their ids name private repos.
The page filters by dataset, agent · model · effort and run day; shows per-arm pass rate and Δ vs control, a
per-task Δ chart (tokens / cost / turns / wall), the task × arm matrix and every trial.
One-time: repo Settings → Pages → Source: GitHub Actions (`.github/workflows/pages.yml`).

## Telemetry

Optional. `cp telemetry.env.example telemetry.env` and set your OTLP endpoints; the file is injected into every
sandbox. Without it trials run the same, only without OTel export. Every trial adds
`OTEL_RESOURCE_ATTRIBUTES=trial.id=…,arm=…,task=…,agent=…`, so:

```logql
{service_name="claude-code"} | trial_id="<trial>"          # Loki: structured metadata trial_id / arm / task
```
```promql
claude_code_token_usage_tokens_total{arm="rtk", task="<id>"}   # Prometheus: labels on every counter
```

Codex: OTel not wired yet (needs `[otel]` block in `~/.codex/config.toml` written during setup).

## Caveats

- Docker injects an ~18 KB `~/CLAUDE.md` (sandbox instructions) into every claude sandbox. Same in both arms, but it
  inflates the cached prefix vs your normal setup.
- Network policy is `allow-all` except GitHub: after setup and tools, each trial gets a sandbox-scoped deny for
  `github.com` and `githubusercontent.com` (agents did `git remote add` + `git fetch --unshallow` to get upstream
  history). Other hosts stay open; tighten with `sbx policy init deny-all` + allows for api.anthropic.com,
  prometheus/loki hosts if you want a hard guarantee.
- Codex + RTK is instruction-based (AGENTS.md); check `rtk-gain.txt` to see whether the agent actually used it.
- Cost in `meta.json` is the agent's client-side estimate.

## Tools

| tool | what the arm gets | notes |
|---|---|---|
| `rtk` | RTK binary + `rtk init -g` (Claude: Bash rewrite hook; Codex: `AGENTS.md`) | `rtk-gain.txt`, `rtk-data/` |
| `serena` | Serena MCP (`serena-agent`, LSP symbol tools) + its recommended hooks; repo pre-indexed during setup | language servers download at setup (GitHub blocked later); project data in `~/.serena`, not the repo; `serena-logs/` has every tool call. Set `SERENA_LANGUAGES` in task `env:` when inference picks a language without a toolchain (iggy C# tasks → `csharp` on the `dotnet` template; Rust tasks → `rust` on the `rust` template). rust-analyzer on the whole iggy workspace takes ~2.5 min to index and up to ~5.6 GB RAM, so iggy Rust tasks use `memory: 6g` |
| `upfront` | no tool: sets `ENABLE_TOOL_SEARCH=false` in `~/.claude/settings.json`, so MCP tools from earlier tools in the arm ship with full schemas on every request instead of as names behind ToolSearch | list it last (`serena-upfront: [serena, upfront]`); no-op for codex. Deferred = "is the tool worth installing as I use it", upfront = "does it help once the model actually uses it"; upfront adds the schemas to every request's (cached) input |
| `graphify` | code-only knowledge graph (`graphify update .`, tree-sitter, no LLM) + `graphify <agent> install` (hooks + rules in the global `CLAUDE.md`/`AGENTS.md`) | `graphify-out/` in the repo root, hidden via `.git/info/exclude`; `graphify-queries.jsonl` logs the agent's queries |

Serena and graphify install their vendors' recommended hooks, which push the agent toward their tools (Serena denies
bursts of Read/Grep; graphify adds a "run graphify query" note to searches). That is the product as shipped; for an
"MCP/graph only" arm, make a copy of the tool without the hook step. Versions are pinned in each `setup.sh` (plus
`uv --exclude-newer` for transitive deps). Tool setup gets the task's `env:`.

## Adding a tool

`tools/<name>/setup.sh` runs inside the sandbox as root with the agent name as `$1` and the repo dir as `$2`
(snapshot and task `setup:` are already there, so the tool can index the repo). Network is open during setup;
GitHub is blocked right after, so download everything now. Install the binary as `<name>` on the PATH with a
working `<name> --version` (recorded in `meta.json` `versions`), then activate for that agent (write
hooks/config as user `agent` via `su agent -c ...`). Pin versions inside the script. Add an arm to `arms.yaml`
(`mine: [<name>]`), or to one task's own `arms:` block.
