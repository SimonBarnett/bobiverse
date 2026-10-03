<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/fr-mode-no-self-merge.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR mode: open PR, never self-merge (FR #343)

## CAST IRON

| Mode | Seat does | Seat must **not** |
|------|-----------|-------------------|
| **FR / implementer** | Open **one** PR vs `main`, post URL, stop | `gh pr merge`, approve+merge own PR, close FR as DONE after self-merge |
| **MRB** | Different seat (or fresh session if only one seat): tests-first hostile review per `bob-mrb-worker` | Author of the PR reviewing/merging their own implementer PR |

## Why

On 2026-09-25 workers opened **and merged** their own FR PRs within seconds (gh-Jeeves #29–#43, agentic_irc #225). README mojibake landed because no independent MRB ran first.

## Rules for packs (Cursor / Grok / Aider / free seats)

1. **FR mode** (ASSIGN FR, implement feature): `gh pr create` → print URL → **DONE stop**. Do **not** `gh pr merge`.
2. **MRB mode** (ASSIGN MRB): follow `bob-mrb-worker`. PASS → merge; FAIL → one fix PR then merge both. Prefer a **different** seat than the PR author; single-seat boxes use a **new session** labeled MRB.
3. Bob alone stamps human UAT.

## Guard

```powershell
# Flag PRs self-merged within N minutes of open (default 30)
powershell -NoProfile -ExecutionPolicy Bypass -File tools\Assert-FrPrNoSelfMerge.ps1 `
  -OwnerRepo SimonBarnett/gh-Jeeves -Pr 42 -Minutes 30 -Json
```

```bash
python tools/fr_self_merge_guard.py --repo SimonBarnett/agentic_irc --pr 225 --minutes 30
```

Exit **2** = self-merge-too-fast flag (MRB-pending / policy break). Exit **0** = ok or not yet merged.  
Jeeves / Bob may announce `MRB-pending: self-merge flag` when exit 2.

GitHub ruleset guidance: require a second reviewer or block merge without `mrb-pass` label when practical; this repo ships the **detect+flag** script for CI/ops.

## Encoding (FR #347)

Same packs: UTF-8 **without BOM**. Helpers: `tools/Utf8NoBom.ps1`. Check: `python tools/check_utf8_mojibake.py --root .`. See `docs/utf8-no-bom.md`.

## Tests

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tests\BT0fr-no-self-merge-343.ps1
python tools/fr_self_merge_guard.py --self-test
powershell -NoProfile -ExecutionPolicy Bypass -File tests\BT0utf8-no-bom-347.ps1
python tools/check_utf8_mojibake.py --root .
```
