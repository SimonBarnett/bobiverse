# Feature request: Jeeves dual Copilot + Weights model

Existing repo: SimonBarnett/bobiverse. Parent surface: open FR-digest #9744 on origin/main (tip cc0f793 at planning time).

The Copilot coding-agent allowance remains the bottleneck for throughput. This request lets Jeeves keep up to two live Copilot tasks concurrently, adds a Copilot agent model picker to the Weights configuration, and shows those jobs on the digest and TipForm once under the Copilot pool.

## Objective

Operators select a Copilot agent model (or omit it for GitHub auto) in the Weights configuration. While allowance remains, Jeeves keeps up to two live Copilot cloud-agent tasks. The digest and TipForm show Copilot jobs once under the Copilot pool (model + current task).

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Concurrent cap | exactly 2 live | copilot_dispatch.tick fills until copilot-jobs.json count reaches 2 or no eligible high-priority row remains | still stops at 1; starts a 3rd while 2 live |
| S2 | Weights picker | Copilot model selectable | GET/PUT /bob/v1/models includes Copilot row with agent, cli, model, context, effort keys; empty model allowed | Copilot row absent; empty model rejected |
| S3 | Dispatch uses model | model on GitHub POST | copilot_dispatch includes model when Weights Copilot model is non-empty; omits model key when empty | always omits when set; sends blank string when empty |
| S4 | Job record | model persisted | each copilot-jobs.json entry has model and start_model fields | job record missing model/start_model |
| S5 | Digest export | tasks array | GET /bob/v1/report digest.copilot.tasks lists live jobs (model, task, repo, id, working_on); empty list when no jobs | tasks missing; duplicated under machines; secrets leaked |
| S6 | Tray paint | once under pool | TipForm Copilot section shows job lines under the Copilot pool bar; jobs not under machines.* | jobs only in JSON; painted twice; painted under machines |

## Shape

Primary: **service**

Jeeves `copilot_dispatch.tick`, `bobreport.build_digest_object`, Weights models catalog, and TipForm sections are surfaces of this request. The product remains the chair service, digest, and tray.

LOCKED

## Stack

Default: existing chair Python modules `common/scripts/copilot_dispatch.py`, `common/scripts/bobreport.py`, `worker/scripts/models_catalog.py`, and tray `bob/tray/src/Public/Get-BobTrayHover.ps1`, plus pytest.

Why: copilot_dispatch and bobreport are the natural homes for concurrency and digest export. Weights is the locked picker. The tray already paints pools.

Why-not: environment variables only (superseded by #9749 Weights lock); a separate queue (dispatch is deterministic); new webhooks.

LOCKED

## Architecture

```
Weights GET/PUT (/bob/v1/models)
  |
  v
copilot_dispatch.tick reads Copilot model, dispatches up to 2 live tasks
  |
  v
copilot-jobs.json (model + start_model per job)
  |
  v
bobreport.build_digest_object exports digest.copilot.tasks
  |
  v
TipForm paints Copilot jobs once under pool
```

Dispatch gates: settle-before-dispatch, existing give-up / high-priority checks, concurrent cap (2). No change to allowance semantics or queue routing.

LOCKED

## Small FR drafts

Distinct issues, one per deliverable. All depend on digest #9744. HOLD is not filed; children unlock per park approval.

| id | issue | title | slice |
|----|-------|-------|-------|
| FR-A | #9745 | Copilot concurrent slot cap 2 | dispatch keeps 2 live, no 3rd; MAX_CONCURRENT_COPILOT = 2 constant |
| FR-B | #9748 | digest.copilot.tasks export | bobreport adds copilot.tasks array; model, task, repo, id, working_on fields |
| FR-C | #9750 | Tray paints Copilot jobs once under pool | TipForm shows Copilot jobs under Copilot pool bar; not under machines.* |
| FR-D | #9746 | Weights Copilot agent + CLI catalog | models_catalog default Copilot row; GET/PUT round-trip; empty model allowed |
| FR-E | #9749 | Dispatch sends Weights Copilot model | dispatch includes model on GitHub POST when set; omits when empty; persist on job record |

## Twin

- #9738 env-only CCA model — closed as superseded by #9749 (Weights locked picker).

## Notes

- Concurrency does not change the allowance exhaustion or high-priority gate logic; dispatch still settles before each send.
- Empty Copilot model in Weights (default) means GitHub auto-selects agent (no model key on POST).
- Jobs show on digest + tray once under the Copilot pool, never under machines.copilot.
- Digest closed by child completion; unhold when all children land on main.

## Testable

- CI: pytest modules asserting concurrent cap (2 live, no 3rd), model round-trip, POST body shape, digest.copilot.tasks array, tray paint (once, under pool).
- Fail-when: dispatch still at 1; Weights Copilot row absent; model always omitted; jobs painted twice; manual-only Testable.
