<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-pr-mrb-cursor-models-transaction-2026-09-20.md, last changed 2026-09-20. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: PR/MRB transaction — Cursor Models first, then grok

**Date:** 2026-09-20
**Repo:** https://github.com/SimonBarnett/agentic_build
**Raised by:** Simon (Spending dashboard + #Bobiverse tray, 20 Sep 21:25)
**UAT + hostile MRB owner:** Bob
**Related:** `bob-build-loop`, `cursor-mrb-dev`, `bob-hostile-mrb`, `box-usage`, `bob-fleet-tray`

## Evidence from the attached dashboard

`cursor.com/dashboard/spending` (Ultra $200/mo, reset 16 Oct) at 21:25 20 Sep 2026:

| Meter | Used | What it is |
|---|---|---|
| **Cursor Models** (Includes Cursor Grok and Composer) | **1%** | The pool for MRB and PRs |
| Other Models | 6% | Claude / GPT / thinking. Not this loop |
| Grok Bot weekly | 100% | Sand. Resets 23 Sep. Not Cursor Models |
| On-Demand | billed later | Overage money, not remaining |

The #Bobiverse tray labelled the top row `Cursor Models (-£54.14) - reset 23 Sep`. That figure is Grok Bot Sand overage, not Cursor Models remaining. Cursor Models still had ~99% left.

## Problem

1. MRB used Other Models (`claude-opus-5-thinking-high`) while Cursor Models sat unused.
2. Workers pushed commits; there was no required PR. Merge was a human/Bob judgment.
3. FAIL did not always spawn a FIX worker. PASS-nits did not always merge.
4. The tray/picker treated Sand remaining as Cursor Models remaining, so the fuel gate could skip Cursor while 99% of Cursor Models was left.
5. The loop still needed an agent to *decide* next steps.

## Ask (deterministic transaction)

No reasoning about who does what. Table in `bob-build-loop`.

1. **Fuel.** If Cursor Models remaining > 0, both the **PR worker** and the **MRB worker** use Cursor Models (Cursor Grok + Composer). If remaining is 0, both use grok.exe. Never Other Models. Copilot only with `-AllowCopilot`.
2. **Show remaining.** Tray top bar and `Get-BobCapacity.cursor_models.remaining_pct` are the Spending **Cursor Models** remaining %, not Sand, not Other Models, not overage GBP.
3. **Hand off both sides.** Bob does not write the MRB and does not implement. Cursor Agent or grok.exe does.
4. **Every worker submits a PR.** Never push `main`. Never self-merge.
5. **PASS-nits:** the **MRB agent** merges that PR (`gh pr merge`). Nits do not block.
6. **FAIL:** do not merge. The dispatcher **immediately** starts a FIX worker on the Required fixes. That worker opens a new PR. Re-MRB. Repeat until PASS-nits.
7. Only **Bob** stamps **ready for human UAT**.

## Models (`config/default.json`)

| Kind | Cursor Models remaining > 0 | Cursor Models remaining = 0 |
|---|---|---|
| mrb | Cursor Grok `grok-4.6` on cursor-agent | grok.exe `grok-4.6` |
| build (PR) | Composer `composer-2.5` | `build0.1` if listed, else `grok-4.5` |

## Acceptance

1. README mermaid and `bob-build-loop` mermaid match the table above.
2. Skills no longer name Other Models / `claude-opus-5-thinking-high` as the MRB model.
3. Worker packets say: open a PR; do not push main; do not merge.
4. MRB packets say: PASS-nits merge; FAIL do not merge, Required fixes only.
5. `models.mrbCursor` is a Cursor Models id (`grok-4.6`), not an Other Models id.
6. Docs name the three Cursor dashboard meters and which one is fuel.
7. Test-Pack green off-DEV.

## Non-goals

- Scraping a new Cursor billing HTTP schema in this pass (meter mapping is the contract; implement the fetch in a follow-up if `Get-CursorAgentUsage.py` still returns Sand).
- Auto UAT stamp.
- MRB PDFs.
- Using Other Models because they "think better".
