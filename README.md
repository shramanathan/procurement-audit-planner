# Procurement Audit Planner: West Berkshire Council

An agentic system, built with Claude Code **Skills + Agents**, that plans an
internal audit of procurement for West Berkshire Council from the council's
public data. It turns the purchasing rulebook into testable rules, analyses the
full spend population against them, folds in past audit history, rates the
risks with the council's own scoring method, and produces a cross-checked audit
planning pack that a human auditor approves and signs off.

> **Indicators, not accusations.** This works on a real council's real data.
> Every output describes *risk indicators to investigate*, never wrongdoing by
> the council, a department or a supplier. A supplier that appears in a flagged
> list or a sample has not been found to have done anything wrong; many flags
> have ordinary explanations (staged payments, recurring fees, several
> placements at the same rate).

The full specification is in [`CLAUDE.md`](CLAUDE.md).

---

## Architecture at a glance

```
                    [contract-rules.pdf]
                            |
             (1) /extract-rules  ← SKILL, invoked by the human
                            |
                       rules.json
                            |
        +-------------------+--------------------+
        |                                        |
 (2) spend-analyst  ← AGENT              findings-analyst ← AGENT
     spend workbooks + contracts.csv         committee PDFs
        |                                        |
   analytics.json                           history.json
        +-------------------+--------------------+
                            |
 (3) risk-assessor ← AGENT, follows the risk-assessment SKILL
     writes risk-ratings.json → build_register.py renders the register
                            |
          risk-register.md + auditor-comments.md
                            |
 (4) HUMAN GATE: the auditor approves / rejects / amends each risk
                            |
 (5) AGENT TEAM: planner (uses the audit-program SKILL)
                 challenger  ⇄  planner  ⇄  qa-reviewer (runs scripts/checks)
                            |
 (6) HUMAN GATE: the auditor signs off review.md
```

The core rule throughout: **the LLM reads and judges; Python computes every
number.** Agents write their judgments to JSON; deterministic builders and
checks turn those judgments into documents and refuse anything untraceable.

---

## The Skills

Skills live in `.claude/skills/<name>/SKILL.md`. Each holds a *method*; two
also ship a Python builder that does the computing and checking.

| Skill | Used by | What it does | Python |
| --- | --- | --- | --- |
| **`extract-rules`** | the human (`/extract-rules`) | Reads the Contract Procedure Rules PDF and writes `outputs/rules.json`: one entry per testable rule with clause, page, thresholds (as printed), required action, approver, evidence source and a **verbatim quote**; unprinted thresholds become named `null` parameters; untestable clauses go to `excluded` with a reason; drafting gaps and contradictions go to `notes`. | `verify_quotes.py` checks every quote is on its stated page, thresholds match the wording, IDs are sequential and every clause is accounted for. Done = exit 0. |
| **`risk-assessment`** | `risk-assessor` agent | The rating method: a likelihood rubric (L1–L5), impact on the council's own Table 1 scale, the council's 5×5 matrix and RAG bands from the Risk Management Strategy, the repeat-finding uplift (only with an adverse audit opinion), the citation rules and the revision workflow after the auditor's decisions. | `build_register.py` resolves every `[rule:]`, `[metric:]`, `[history:]` citation and `{{$.path}}` placeholder, computes score/label/band/escalation, drops uncited risks, warns on typed figures, enforces the revision rules, and renders `risk-register.md` and the auditor's decision template `auditor-comments.md`. |
| **`audit-program`** | `planner` agent | How to turn approved risks into expected controls (each citing a rule), test steps (each citing a rule or metric), sample recipes (source file, filter, sort, method) and PBC request items, written to `outputs/audit-plan.json`. | `build_pack.py` checks the auditor gate, resolves citations, sizes samples by the risk's score, draws them deterministically, verifies every sampled payment exists in the cleaned data, checks control/test/rule coverage and renders `planning-memo.md`, `risk-control-matrix.md`, `audit-program.md`, `outputs/samples/T-*.csv` and `pack-figures.json`. `--gate` runs only the gate check. |

## The Agents

Agents live in `.claude/agents/*.md`. Each file sets the agent's tools, the
files it may touch, and its report. All six have project memory for *how-to
lessons only* (`.claude/agent-memory/`), never evidence or judgments.

| Agent | Step | Reads | Owns (writes) | Role |
| --- | --- | --- | --- | --- |
| **`spend-analyst`** | 2 | `rules.json`, `data/spend/*.xlsx`, `data/contracts.csv` | `scripts/*.py`, `outputs/analytics.json`, `outputs/analytics-full/` | Writes and runs Python to clean the monthly workbooks and parse the Contracts Finder export, then runs the tests: threshold clustering, split purchases, off-contract spend, duplicates, spend after notice expiry, spend vs award. Thresholds come from `rules.json`, never hard-coded. |
| **`findings-analyst`** | 2 | `data/committee/*.pdf` | `outputs/history.json` | Records past audit opinions, agreed actions, risk themes and the council's risk-scoring method, each with source file, page and a copy-exact quote. Records, never scores. |
| **`risk-assessor`** | 3 | rules, analytics, history | `outputs/risk-ratings.json` | Follows the `risk-assessment` skill; reruns `build_register.py` until PASS with 0 warnings. Recommends only; applies the auditor's Approve / Reject / Amend in numbered revisions. |
| **`planner`** | 5 (team) | register, decisions, rules, analytics | `outputs/audit-plan.json` | Follows the `audit-program` skill; builds until PASS; announces `PACK READY vN`; answers each `CHALLENGE #n` with `accepted / declined / for the auditor`; fixes each `QA vN: FAIL`; ends with `PLANNER DONE vN`. Never re-rates a risk or changes scope. |
| **`challenger`** | 5 (team) | register, decisions, inputs, the pack | `outputs/challenges.md` | Sends up to eight cited challenges, then up to four in a second round (types: rating, scope → for the auditor; sample, control, test, coverage → for the planner); verifies accepted changes in the rebuilt pack; closes every row; ends with `CHALLENGER DONE`. Never reads raw data. |
| **`qa-reviewer`** | 5 (team) | everything, via the checks | `outputs/review.md` | Runs `scripts/checks/run_checks.py` on every pack version, sends each failure to its owner, and after both teammates are done writes `review.md`: results as printed, verdict READY FOR SIGN-OFF or BLOCKED, and a blank auditor sign-off block. Fixes nothing, softens nothing. |

### QA checks (`scripts/checks/`)

Written independently of the builders, so a builder bug can't hide itself.

| Script | Checks |
| --- | --- |
| `check_quotes.py` | runs the extract-rules verifier against the PDF; every rule reference/excerpt in the register matches `rules.json` |
| `check_numbers.py` | every £ figure or 3+ digit number in the three documents is a value in `analytics.json`, `pack-figures.json`, `rules.json` or the samples |
| `check_trace.py` | rule → risk → control → test is complete; every High/Extreme risk is in scope or rejected with a reason; `challenges.md` rows cite evidence and none is open |
| `check_samples.py` | every sampled payment is in `spend_clean.csv` **and** at its exact row in the council's workbook, same supplier and amount |
| `run_checks.py` | runs all of them; one table and a verdict |

---

## How they work together

1. **Rules (Skill, human-invoked).** `/extract-rules` produces a verified
   `rules.json`. Everything downstream cites rules by ID.
2. **Evidence (two Agents in parallel).** The spend-analyst computes the
   indicators from the full spend population; the findings-analyst extracts
   audit history and the council's scoring method. Neither rates anything.
3. **Rating (Agent + Skill + builder).** The risk-assessor judges themes and
   rubric rows in `risk-ratings.json` using placeholders and citations only;
   `build_register.py` fills every figure, computes every score and refuses
   uncited claims. The output is a register plus a decision template.
4. **Human gate.** The auditor fills `auditor-comments.md` (Approve, Reject or
   Amend per risk, plus a dated sign-off line). The risk-assessor applies the
   decisions as a numbered revision; the builder checks that exactly those
   changes were made and keeps a decision log.
5. **Agent team.** The lead (main session) runs `build_pack.py --gate`, then
   spawns the planner, challenger and qa-reviewer. They coordinate by
   messages, not through the lead:
   `PACK READY vN` → `CHALLENGE #n` / `RESPONSE #n` → rebuild →
   `QA vN: PASS|FAIL` → `PLANNER DONE` + `CHALLENGER DONE` → final QA run →
   `QA DONE vN: READY FOR SIGN-OFF | BLOCKED`. BLOCKED goes back to the
   team, never to the auditor; a question only the auditor can decide goes
   back through step 4.
6. **Human sign-off** at the end of `outputs/review.md`.

**What keeps it honest:** agents never type figures (`{{$.path}}`
placeholders are filled by code); every claim carries a citation that must
resolve; samples are drawn by code from the flagged lists and checked against
the source workbooks; each agent may write only its own file; and failures
stop the pipeline instead of being worked around.

---

## Results in this repository

| Stage | Output | Result |
| --- | --- | --- |
| 1 | `outputs/rules.json` | 78 testable rules, 41 clauses excluded with reasons, 4 unprinted thresholds as null parameters, 21 drafting notes; verifier passes |
| 2 | `outputs/analytics.json`, `outputs/history.json` | 7 spend tests over the full 3-month population; audit opinions and the council's 5×5 scoring method with page-level sources |
| 3–4 | `outputs/risk-register.md` | 10 risks rated; after 6 revisions of auditor decisions, 9 approved and 1 rejected (grants, to be covered by a separate review) |
| 5 | `outputs/planning-memo.md`, `risk-control-matrix.md`, `audit-program.md`, `samples/` | pack v5: 22 controls, 16 tests, 14 sample files, 3,955 sampled payments; 8 challenges (7 resolved, 1 declined); QA 5 of 5 checks pass |
| 6 | `outputs/review.md` | READY FOR SIGN-OFF; signed off by the auditor |

## Running it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # pandas, openpyxl
# needs poppler (pdftotext, pdfinfo) for the PDF steps
claude            # Claude Code in this folder; agent teams enabled in .claude/settings.json
```

Then, in order: `/extract-rules`; ask for the spend-analyst and the
findings-analyst; ask for the risk-assessor; fill in
`outputs/auditor-comments.md` and rerun the risk-assessor until every risk is
decided; ask Claude to run the agent team (it follows the lead procedure in
`CLAUDE.md`); sign off `outputs/review.md`. Builders and checks can be run on
their own:

```bash
.venv/bin/python .claude/skills/risk-assessment/build_register.py
.venv/bin/python .claude/skills/audit-program/build_pack.py --gate
.venv/bin/python .claude/skills/audit-program/build_pack.py
.venv/bin/python scripts/checks/run_checks.py
```

## Live deployment (fly.io)

**https://wbc-procurement-audit-planner.fly.dev/**

`web/app.py` (Flask) serves two things:

- **The reference run**: the signed-off pack in `outputs/` as web pages, the
  sample downloads, and **Live QA**, which reruns `build_pack.py --gate` and
  `scripts/checks/run_checks.py` on the server.
- **New runs** (`/runs`): anyone with an **access code** can start the whole
  pipeline again on the bundled council data. `web/runner.py` runs Claude Code
  headless (`claude -p`) in a fresh copy of the project for each run:
  1. the `extract-rules` skill, then `spend-analyst` and `findings-analyst` in
     parallel, then `risk-assessor` (`--agent`);
  2. **auditor decisions** on a web form (Approve / Reject / Amend per risk);
     the risk-assessor applies them as revisions until the gate opens;
  3. the **agent team**: `planner`, `challenger` and `qa-reviewer` each run in
     their own resumable session; the runner is the lead and relays their
     messages word for word (`PACK READY`, `CHALLENGE`/`RESPONSE`, `QA vN`,
     `DONE`), because headless Claude Code can't keep background teammates
     alive;
  4. **auditor sign-off** on a web form.

  One run at a time; each Claude Code call is capped with `--max-budget-usd`
  and a run stops at `RUN_BUDGET_USD` (default $40). The run page shows live
  agent activity, cost per call, the documents and samples. Runs are kept on
  a fly volume.

Secrets (set once): `ANTHROPIC_API_KEY` and `ACCESS_CODES` (comma-separated).

```bash
fly secrets set ANTHROPIC_API_KEY=... ACCESS_CODES=code1,code2
fly deploy --remote-only        # Dockerfile + fly.toml in the repo root
.venv/bin/python web/app.py     # run locally on http://127.0.0.1:8080
```

## Repository layout

```
CLAUDE.md                     full system specification
.claude/settings.json         enables agent teams
.claude/skills/               extract-rules, risk-assessment, audit-program (+ builders)
.claude/agents/               the six agents
.claude/agent-memory/         per-agent how-to lessons
data/                         council source files (public, read-only)
scripts/                      spend-analyst's Python; scripts/checks/ = QA checks
outputs/                      every artefact listed above
web/                          fly.io web viewer (Dockerfile, fly.toml in the root)
```

## Data sources

All public West Berkshire Council material, downloaded manually: the Contract
Procedure Rules (constitution Part 8, September 2025); the "Expenditure over
£500" monthly workbooks (3 months); a Contracts Finder export of the council's
awarded notices; and Governance Committee papers (internal audit
completed-work appendices, Internal Audit Plan 2025–28, Risk Management
Strategy 2024–2027). The Strategic Risk Register is exempt and was not used.

---

## Confirmation: steps of the guide completed

- [x] **Project set-up**: `CLAUDE.md` specification, Python environment, data in `data/` (read-only).
- [x] **Skill `extract-rules`** built and run; `rules.json` passes the quote verifier.
- [x] **Agent `spend-analyst`** built and run; `analytics.json` + full lists + a self-check that re-derives one flagged item per test.
- [x] **Agent `findings-analyst`** built and run; `history.json` with sourced audit history and the council's scoring method.
- [x] **Skill `risk-assessment`** with `build_register.py`.
- [x] **Agent `risk-assessor`** built and run; register built with PASS and 0 warnings.
- [x] **Human gate**: auditor decisions recorded and applied as numbered revisions (Approve, Reject, new risks requested), each override and addition flagged in the register.
- [x] **Gate closed**: every risk decided; `build_pack.py --gate` opens.
- [x] **Agent teams enabled** (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in `.claude/settings.json`).
- [x] **Skill `audit-program`** with `build_pack.py`, tested on a two-risk fixture (fails on a missing risk, an uncited control and an unaccounted rule).
- [x] **Agents `planner`, `challenger`, `qa-reviewer`** with the message protocol.
- [x] **QA scripts** in `scripts/checks/`, each tested on the real outputs and on fixtures with planted faults (bad figure, missing row, tampered amount, unaccounted rule, open challenge, wrong clause, altered quote).
- [x] **Agent team run**: gate check, challenge rounds, QA rounds, all three report done, team shut down.
- [x] **Final human sign-off** recorded in `outputs/review.md`.

Counts and file names differ from the guide's example run, as the guide
allows: the register reached revision 6 with 10 risks, because the auditor
requested two new risks, rejected one and brought one challenge (care-placement
duplicate payments) into scope as a new risk before sign-off.

**Notes on the run.** In this Claude Code build the Agent tool could not give
teammates names, so the three teammates addressed each other by agent ID
(still directly, not relayed by the lead). During the team runs the planner
reported a builder bug (a payment-level sample labelled by supplier); it was
fixed in `build_pack.py` and the pack went back through the team and QA.
