---
name: bobiverse-jeeves-agent-fr-digest
description: >
  Jeeves / MONITORING playbook for the FR digest go-gate (BOB-G* / CI-G*):
  fr-digest + hold blocks children; unhold alone releases; CI fails open
  children still Depending-on a parent FR. Use when fr-digest, digest go-gate,
  unhold-releases, BOB-G1 G2, CI-G1 CI-G2, VIS-G, or /bobiverse-jeeves-agent-fr-digest.
  When BOB-G is live, every monitor cycle runs this node after depends-on.
depends_on:
  - bobiverse-jeeves-monitor
  - bobiverse-jeeves-agent-depends-on
---

# bobiverse-jeeves-agent-fr-digest

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

Theme index: BOB-G1 #8837, BOB-G2 #8838, CI-G1 #8839, CI-G2 #8841. Vision packs on branch `docs/fr-digest-go-gate-frs-2026-11-21`. Product Depends-on parse/skip (BOB-D1 #8805, D3 #8807) must land before G1 offer behaviour.

## Three gates (net result, confirmed)

| Gate | Mechanism |
|---|---|
| 1 | Label `hold` - manual park |
| 2 | `Depends-on: #N` all **CLOSED** (BOB-D*) - see `bobiverse-jeeves-agent-depends-on` |
| 3 | **This skill:** digest issue labeled `fr-digest` (+ usually `hold`); children `Depends-on: #digest`; while digest has `hold`, skip children (`depends-held`); **unhold alone releases** (close optional); CI fails PRs whose FR still has open children Depending-on it |

## Encoding (LOCKED)

- One digest issue per target repo for a batch park
- Digest labels: `fr-digest` and `hold` (Plan parks on hold)
- Children: `Depends-on: #digest` (and optional intra-batch Depends-on among children)
- Offer path: parse Depends-on -> if depend has `hold` skip `depends-held` -> else if depend is `fr-digest` without hold, allow even while OPEN -> else OPEN skip (D3)
- CI: open issues that still `Depends-on` the PR's FR => fail build-jeeves (CI-G1/G2)

## When live (monitor cycle)

Run **after** `bobiverse-jeeves-agent-depends-on` each cycle once BOB-G1 is on tip:

1. List open issues with label `fr-digest`. Note which still have `hold`.
2. For each digest, find children (open issues whose body Depends-on that `#N`).
3. **Finding:** child offered/accepted while digest still has `hold` -> intake (comment on #8837).
4. **Not a finding:** child correctly skipped with `depends-held`; or digest unheld and child offered while digest still OPEN (go-gate working).
5. **CI:** if build-jeeves fails open-children gate, comment on #8839/#8841 with PR number; do not invent a twin FR.
6. Prefer script when present: `Invoke-JeevesMonitorCheck.ps1 -Check fr_digest` (FR filed with this skill).
7. CAST IRON point 5: when the fr-digest monitor playbook is proven, FR the durable check into the token-less chair (`tools\monitor\fr_digest.py` + wrapper + chair go-gate) so it runs without an LLM.

## Until BOB-G is live

- Keep G*/CI-G* on `hold` until Simon unholds.
- Do not treat missing go-gate as a chair bug yet - product is park-only.
- Still load this skill so the monitor is ready the turn D/G ship.

## Hard rules

- No secrets. Public hosts only.
- Never edit queue/ledger/digest by hand.
- No chair commands unless FR #8827 is live and the action keeps the queue moving (e.g. unhold is a **human/Plan** action - monitor does not remove `hold` labels unless Si said so).
- Do not edit parked VIS-D* / BOB-D* bodies from this skill.

## Output (required when this node runs)

| digest | hold? | child | child state | chair/CI | ok? | evidence | existing issue |
|---|---|---|---|---|---|---|---|

Empty table with `no fr-digest batches in flight` is valid.

## Refs

- G1 offer: #8837
- G2 docs: #8838
- CI-G1/G2: #8839 / #8841
- Depends-on parse/skip: #8805 / #8807
- Sibling: `bobiverse-jeeves-agent-depends-on`
- Live MONITORING loop: `bobiverse-jeeves-monitor`, `monitor-start`
