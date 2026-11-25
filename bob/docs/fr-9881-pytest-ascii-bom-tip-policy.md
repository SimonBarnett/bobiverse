# FR #9881: pytest-ascii-bom soft tip proceed + Prefer (A) writers

## What
Tip PR #9788 stayed BLOCKED on `pytest-ascii-bom` while `build-jeeves` was green.
Tip/MRB must not uniquely BLOCK on soft-only `failure:pytest-ascii-bom` when
`build-jeeves` is green. Prefer (A): harden BOM-less writers so new tips do not
reintroduce non-ASCII / BOM.

## Soft tip proceed (code)
`common/scripts/mrb_merge_on_green.py`:

- Soft markers: `pytest-ascii-bom` / `ascii-bom`
- Rollup annotates soft-only red as `failure:pytest-ascii-bom`
- `tip_may_proceed_soft_ascii_bom(checks, build_jeeves_green=True)` gates proceed
- `decide_merge_on_green` returns `wait` (not `requeue_ci`) for soft-only
- `fix_ci_skip_reason` returns `soft-allow-ascii-bom` so FIX-CI is not uniquely queued

Hard reds (for example `build-jeeves` failure together with ascii-bom) still
rollup as bare `failure` and keep the normal FIX / requeue path.

PR #9933 (Refs #9881) soft-allows the same marker for CI-red MRB-hold reset; this
note closes Prefer (A) tip proceed + writer hygiene with `Closes` #9881.

## Prefer (A) durable writers
- `Write-BobiversePs1AsciiNoBom.ps1` / `bobiverse_ps1_ascii.py write` for `*.ps1`
- `Write-BobiverseUtf8NoBom.ps1` / `New-Object System.Text.UTF8Encoding $false`
  for gh `--body-file` / comment files (never `Set-Content -Encoding utf8`)
- Pre-push: `Assert-BobiverseChangedPs1Ascii.ps1`
- Workflow: `.github/workflows/pytest-ascii-bom.yml` (job name stays required)

## Ops
Ruleset still requires `pytest-ascii-bom` (FR #9217). Soft proceed does not waive
the required check for GitHub merge; it stops tip/MRB from uniquely parking FIX
when only that check is red and `build-jeeves` is green. Clear the red with Prefer (A).
