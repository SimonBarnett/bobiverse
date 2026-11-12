# Vision: CLI token comparison on the Jeeves appliance

Feature request on `SimonBarnett/bobiverse`. Gap base: `origin/main` `b429d9b1`.
No new repo. Shape stays the chair service.

## Objective

A finished Grok or Cursor CLI job records the same measured token fields OpenCode already records, those rows can be compared by model, and the Jeeves appliance status page draws that comparison.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Grok CLI model tokens | A fixture `usage.json` whose `modelUsage` entry has input 100, output 20, cached 5 produces a DONE stamp `tokens_in=100 tokens_out=20 tokens_cached=5` and `model=` set to that entry. The ledger row matches. | `pytest` on `done_usage` and worker `measure_done_usage` with the fixture. No live xAI call. | The file has those counts and the stamp is `tokens=unknown`, or the counts are attributed only to `primaryModelId` while `modelUsage` names a different model. |
| S2 | Cursor CLI tokens | A non-zero local or fixture source for that chat stamps the same three fields and `model=`. A missing source, or a store whose token fields are absent or zero, stamps `tokens=unknown`. | `pytest` with a counts fixture and a zero or missing fixture. | A zero local store becomes `tokens_in=0`, or a non-zero fixture is dropped. |
| S3 | Model comparison | Two measured Grok rows, one measured Cursor row, and one unknown row roll up to two model buckets. Token sums match the measured rows. `unknown_jobs` is 1 and is not added into the token sums. | `pytest` on the ledger rollup in `common/scripts/job_cost_ledger.py`. | Models are merged into one bucket, or unknown jobs are counted as zero tokens. |
| S4 | Appliance token graph | The status page renders three states: a by-model token series when rows exist, an empty state when no measured row exists, and an error state when the ledger cannot be read. | `pytest` renders the three HTML bodies. Mocks: `bob/docs/mocks/cli-token-compare/home.html`, `empty.html`, `error.html`. | `/status` still shows only fuel names, or the empty ledger draws a zero-valued series. |

LOCKED

## Shape

Primary: **service**

Hybrid note: ircJeeves remains the product. The appliance status page is an existing chair companion. These graphs extend that page.

LOCKED

## Stack

Default: chair Python in `common/scripts/done_usage.py`, `common/scripts/job_cost_ledger.py`, and `common/scripts/jeeves_settings_http.py`, plus the worker DONE stamp in `bob/scripts/bob_worker.py`. Graphs are inline SVG fed by a read-only JSON rollup.

Why: the stamp, the ledger, and the status page already exist.

Why-not: a chart SaaS, a new frontend, or the Cursor dashboard Admin API. Dollar cost and `costUsdTicks` stay out.

LOCKED

## Architecture

Who talks to what. Readers take model ids and token fields only. They do not read auth files, prompts, or API keys. A missing counter stays `tokens=unknown`.

```
Grok usage.json modelUsage ----+
Cursor local or fixture source -+--> worker measure_done_usage
OpenCode opencode.db (already) -+         |  tokens=unknown if missing
                                          v
                                    DONE stamp (existing)
                                          v
                               job-cost-ledger.json (existing)
                                          |
                     +--------------------+--------------------+
                     v                                         v
          digest job_costs.by_model                    appliance /status
          (comparison rollup)                          inline SVG
                                                       home | empty | error
```

LOCKED

## Screens

HTML mocks in `bob/docs/mocks/cli-token-compare/`. No PNGs. This folder is separate from `jeeves/docs/mocks/home.html` and from `bob/docs/mocks/digest-fuel/`.

| id | file | state |
|----|------|-------|
| M1 | bob/docs/mocks/cli-token-compare/home.html | two model series, unknown count not drawn as zero |
| M2 | bob/docs/mocks/cli-token-compare/empty.html | no measured rows |
| M3 | bob/docs/mocks/cli-token-compare/error.html | ledger unreadable, no invented series |

## Already on origin/main

- OpenCode reads `opencode.db` per job directory (FR #6420) and stamps DONE (FR #6387). Per-job delta is FR #6435.
- Grok `read_grok_usage` reads session totals and `primaryModelId`. It does not walk `modelUsage` (still true at `b429d9b1`).
- Cursor stamps only `BOB_CURSOR_USAGE_PATH` or `run/cursor-usage.json`. No live store reader.
- Digest `job_costs` is the last 20 PRs, not a by-model series.
- Appliance `/status` lists version, uptime, queue, seats, and fuel names. No token graph.
- `jeeves/VISION.md` still says chair companions are not a website. Shape stays service.
- Open appliance pack #6751 and siblings paints pool remaining percent. FR #6759 drops token fields. That pack is not this comparison.

## Out of scope

- Reworking the OpenCode sqlite reader.
- Dollar cost, pricing tables, or `costUsdTicks`.
- Cursor cloud usage export.
- Pool-percent pages (#6759, #6760, #6761, #6762).
- MSI rebuild, service restart, UAT stamp, IRC.

## UNKNOWN

- Whether any current Cursor CLI build writes non-zero token counts on disk. S2 accepts either outcome. A cloud export is a later request only if the owner names that source.
- Several `modelUsage` entries in one Grok session. S1 is the single-entry case: the stamp model is that entry, not a different `primaryModelId`. More than one counted entry is not this request.

## LOCKED

- Objective, Success S1-S4, Shape service, Stack, Architecture.
- Unknown counts stay unknown. Never stamp a fabricated zero.
- Comparison rollup key: `job_costs.by_model`.
- Graphs are inline SVG on the existing appliance status page, same auth as `/status`.

## Issues

Refs, not a closing keyword. Each stays open for implementation.

| id | issue | mirror |
|----|-------|--------|
| S1 | #6781 | bob/docs/fr/cli-token-compare/FR-001-grok-model-usage.md |
| S2 | #6782 | bob/docs/fr/cli-token-compare/FR-002-cursor-token-source.md |
| S3 | #6783 | bob/docs/fr/cli-token-compare/FR-003-ledger-by-model.md |
| S4 | #6784 | bob/docs/fr/cli-token-compare/FR-004-appliance-token-graph.md |
| docs | #6785 | bob/docs/fr/cli-token-compare/FR-005-vision-hybrid-note.md |
