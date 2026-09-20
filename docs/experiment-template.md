# Token-savings experiment preregistration and result template

Copy this Markdown file for each frozen experiment. Complete it before paid confirmatory runs. Do not
edit preregistered fields after looking at confirmatory results; add dated amendments instead.

## Identity

| Field | Value |
|---|---|
| Experiment ID | |
| Owner | |
| Preregistered at | |
| Protocol commit/hash | |
| Artifact root | |
| Randomization seed | |
| Analysis freeze date | |

## Question and claim

**Tool/treatment:**

**Exact vendor claim being tested:**

**Claim surface:** raw bytes / agent-visible output / input tokens / total tokens / dollars / latency /
quality / other

**Target workload and population:**

**Minimum useful effect:**

**Why this threshold matters operationally:**

## Hypotheses

**Primary efficiency hypothesis:**

**Quality non-inferiority hypothesis and margin:**

**Safety/compatibility hypothesis:**

**Expected mechanism:**

**Expected mechanical ceiling from transcript replay:**

## Frozen environment

| Component | Exact version, digest, or setting |
|---|---|
| Host OS / architecture | |
| `sbx` | |
| Sandbox template digest | |
| Sandbox mode | clone / mountless |
| CPU / memory / disk | |
| Skills sharing | disabled |
| Network policy hash | |
| Agent CLI | |
| Model full identifier | |
| Reasoning effort | |
| Service tier | |
| Authentication type | API key / OAuth / subscription |
| Optimizer binary checksum | |
| Optimizer integration/config hash | |
| Timeout / turn / budget cap | |
| Subagent policy | |
| MCP/plugins/hooks other than treatment | none / list |
| Price manifest date/hash | |

## Arms

| Arm | Agent-visible configuration | Inert/common components | Treatment activation |
|---|---|---|---|
| Control | | | None |
| Treatment | | | |

Confirm that labels such as `control`, `treatment`, `rtk`, or `optimized` are not visible to the agent.

## Tasks

| Stratum | Task IDs | Count | Grader | Network required? |
|---|---|---:|---|---:|
| Shell/test/build heavy | | | | |
| Source-navigation heavy | | | | |
| Mixed implementation/debug | | | | |
| Low-output negative control | | | | |
| Adversarial filter behavior | | | | |

**Frozen task-set hash:**

**Exclusions decided before running:**

**Hidden-test protection:**

## Run ladder and stopping rules

| Stage | Tasks | Repetitions per arm | Purpose | Continue when |
|---|---:|---:|---|---|
| Transcript replay | | N/A | Estimate reachable surface | Instrumentation is complete |
| Deterministic fixtures | | N/A | Validate transformation and exit semantics | Invariants pass |
| Wiring smoke | 5–10 | 1 | Validate environment/artifacts/adoption | All wiring gates pass |
| Variance pilot | 10–20 | >=3 | Estimate variance and sample size | Power/cost is acceptable |
| Confirmatory | | | Test preregistered endpoints | Planned sample completes |

**Futility rule:**

**Harm rule:**

**Maximum experiment spend:**

**Treatment/setup failure policy:** retain / pairwise exclude / score as failure / other

**Timeout policy:**

**Retry policy:**

## Randomization and pairing

**Pairing key:** agent + model + effort + task + repetition block

**Arm-order randomization method:**

**Concurrency policy:**

**Maximum time separation within a pair:**

**Prompt-cache/order mitigation:**

## Primary endpoints

| Endpoint | Exact formula | Source | Direction |
|---|---|---|---|
| Quality-constrained cost | | | Lower is better if non-inferior |
| Cost per successful task | | | Lower is better |
| Correctness | | | Higher is better |

## Secondary endpoints

| Endpoint | Exact formula | Source |
|---|---|---|
| Uncached/new input | |
| Cache creation | |
| Cache reads | |
| Output tokens | |
| Reasoning tokens | |
| Total turns/model requests | |
| Wall time | |
| Treatment adoption | |
| Agent-visible output bytes | |
| Re-read/retry/fallback rate | |
| Compactions | |
| Operational failures | |

Preserve native token fields. Define derived formulas separately for each harness; do not force Claude
and Codex usage into one ambiguous `input_tokens` field.

## Statistical plan

**Unit of analysis:** paired task attempt

**Primary estimator:**

**Confidence interval method:**

**Primary statistical test:**

**Quality test:**

**Multiple-comparison treatment:**

**Outlier policy:** retain by default; any exception must be defined here

**Missing/errored pair policy:**

**Planned subgroup analyses:** exposure stratum / adoption / agent / effort / other

**Power or precision target derived from pilot:**

## Per-trial manifest checklist

- [ ] Trial ID, pair ID, task ID, repetition, and randomized arm
- [ ] Prompt hash and task starting commit/tree hash
- [ ] Host, `sbx`, template, agent, model, effort, and optimizer identity
- [ ] Network/policy, resource limits, and authentication type
- [ ] Coordinator start/end time and process exit status
- [ ] Structured agent output plus separate stdout/stderr
- [ ] Native session logs and all subagent logs
- [ ] Treatment adoption/audit data
- [ ] Final patch/tree hash
- [ ] Independent grader output and exit status
- [ ] Failure/exclusion reason from a fixed vocabulary
- [ ] Artifact checksums completed before sandbox removal

## Wiring gates

- [ ] Fresh sandbox and clean task state confirmed
- [ ] Clone or mountless mode confirmed; no direct writable host checkout
- [ ] Shared skills disabled
- [ ] No undeclared user config, memory, plugin, hook, MCP, or fallback model
- [ ] Model and agent versions match the manifest
- [ ] Control contains no treatment instructions or active hook
- [ ] Treatment fired, with evidence captured
- [ ] Agent usage agrees with session-log totals within the stated tolerance
- [ ] Exit codes survive the collection path
- [ ] Hidden grader is inaccessible to the agent
- [ ] Artifacts survive teardown

## Results

### Sample accounting

| Item | Control | Treatment |
|---|---:|---:|
| Planned attempts | | |
| Completed attempts | | |
| Passed tasks | | |
| Timeouts | | |
| Setup failures | | |
| Agent failures | | |
| Grader failures | | |
| Preregistered pair exclusions | | |

### Primary results

| Endpoint | Control | Treatment | Paired effect | 95% CI | p-value | Decision |
|---|---:|---:|---:|---:|---:|---|
| Correctness | | | | | | |
| Cost per attempt | | | | | | |
| Cost per successful task | | | | | | |

### Mechanism results

| Metric | Control | Treatment | Paired effect | Notes |
|---|---:|---:|---:|---|
| New/uncached input | | | | |
| Cache creation | | | | |
| Cache reads | | | | |
| Output | | | | |
| Reasoning | | | | |
| Turns | | | | |
| Agent wall time | | | | |
| Eligible shell calls | | | | |
| Actually optimized calls | N/A | | | |
| Optimizer self-reported saving | N/A | | N/A | Diagnostic only |

### Outcome by exposure stratum

| Stratum | Pairs | Quality delta | Cost/token delta | Adoption | Interpretation |
|---|---:|---:|---:|---:|---|
| Shell/test/build heavy | | | | | |
| Source-navigation heavy | | | | | |
| Mixed | | | | | |
| Low-output negative control | | | | | |
| Adversarial | | | | | |

## Deviations and amendments

Record every deviation with timestamp, reason, affected trials, whether outcomes were already seen,
and how it will be handled. Never rewrite the original preregistration silently.

| Timestamp | Change | Reason | Outcomes already seen? | Analysis treatment |
|---|---|---|---:|---|
| | | | | |

## Verdict

Choose one and justify it against the preregistered thresholds:

- [ ] Win: practically meaningful saving with non-inferior quality
- [ ] No useful effect
- [ ] Loss: cost, quality, or operational harm
- [ ] Inconclusive: protocol or precision failure

**Intention-to-treat conclusion:**

**Adoption-adjusted diagnostic conclusion:**

**Does the vendor claim match the measured claim surface?**

**Recommended production action:** adopt / targeted opt-in / reject / retest after named change

**Replication package location and hash:**

