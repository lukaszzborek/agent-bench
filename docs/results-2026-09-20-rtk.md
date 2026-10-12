# 2026-09-20 — RTK 0.49.0 vs control, first full run

Claude Code 2.1.278, `claude-sonnet-5`, effort `medium`, sbx v0.43.0. 11 tasks (5 public, 6 private), **n=1 per
arm**, `--jobs 2`. GitHub blocked for the agent in both arms. Exploratory: with one trial per cell, per-task
differences are inside run-to-run noise; only the direction of the totals is worth reading.

| task | pass c / rtk | cost c | cost rtk | Δ cost | tokens c | tokens rtk | Δ tokens | turns c / rtk | wall c / rtk |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| iggy-binarymapper-dos | 1 / 1 | $0.808 | $0.939 | +16% | 2.32M | 2.51M | +8% | 34 / 34 | 264s / 268s |
| iggy-git-diff-csharp | 1 / 1 | $0.097 | $0.160 | +65% | 355k | 350k | −2% | 7 / 7 | 25s / 18s |
| iggy-git-log-csharp | 1 / 1 | $0.072 | $0.192 | +167% | 250k | 457k | +82% | 5 / 9 | 23s / 24s |
| iggy-git-pickaxe-csharp | 1 / 1 | $0.143 | $0.181 | +27% | 297k | 352k | +18% | 6 / 7 | 14s / 19s |
| iggy-utf8-identifier | 1 / 1 | $1.081 | $0.893 | −17% | 2.88M | 2.35M | −18% | 35 / 30 | 198s / 174s |
| private-1 | 1 / 1 | $3.547 | $3.186 | −10% | 12.06M | 6.93M | −43% | 89 / 53 | 502s / 560s |
| private-2 | 0 / 0 | $5.446 | $5.297 | −3% | 16.68M | 15.18M | −9% | 107 / 81 | 997s / 1324s |
| private-3 | 1 / 1 | $1.204 | $1.177 | −2% | 2.08M | 2.18M | +5% | 29 / 30 | 259s / 286s |
| private-4 | 0 / 0 | $2.572 | $3.305 | +29% | 5.34M | 8.12M | +52% | 53 / 80 | 752s / 779s |
| private-5 | 1 / 1 | $3.276 | $2.390 | −27% | 11.34M | 7.58M | −33% | 91 / 99 | 354s / 283s |
| private-6 | 0 / 1 | $0.619 | $0.717 | +16% | 343k | 615k | +79% | 7 / 10 | 133s / 175s |
| **total** | **8 / 9** of 11 | **$18.87** | **$18.44** | **−2.3%** | **53.96M** | **46.62M** | **−13.6%** | 463 / 440 | 3521s / 3909s |

c = control. Tokens = input + cache read + cache write + output. Cost is the agent's client-side estimate.

- Overall RTK is a wash on cost (−2.3%) with fewer tokens (−13.6%); the saved tokens are mostly cheap cache reads.
- Direction splits by task size: RTK costs more on the short git-history tasks and less on the long multi-turn
  tasks (private-1, private-5, iggy-utf8-identifier).
- On the short tasks the cost gap is mostly prompt-cache writes, not work: `iggy-git-diff-csharp` has equal
  tokens and turns in both arms, but 4.3k cache-write tokens in control vs 19.9k in rtk. Whether the ~20k-token
  prefix is already cached when a trial starts depends on what ran just before it, and the rtk arm has its own
  prefix (`@RTK.md` in `CLAUDE.md`). This is a confound of trial order, so do not read those Δ cost values as an
  RTK effect.
- `wall_s` is skewed by `--jobs 2`; the `iggy-utf8-identifier` control trial was rerun alone after a Docker Hub
  auth error killed `sbx create`, so its wall time is not comparable to the rtk one.
- `private-4` fails in both arms with "Zero tests ran" in the grader, which points at the
  grade command rather than the agents. Treat that row's pass column as unverified.
- An earlier run the same day used RTK 0.43.0, which rewrote `git log` inside pipes and capped it at 50 commits.
  The agent then saw a truncated history, decided the shallow snapshot was incomplete and fetched the full
  upstream repo from GitHub (3–4× the tokens of control on the git tasks). 0.44.0+ leaves piped commands raw;
  those results were discarded and the GitHub block was added.
