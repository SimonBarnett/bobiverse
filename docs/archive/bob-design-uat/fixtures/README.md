<!-- ARCHIVED COPY - source: SimonBarnett/bob-design-uat @ 1acf2a3, path fixtures/README.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Fixture pack (issues #3 + absorbed #5)

Repeatable calibration for `design-uat`. Each case is a folder:

```
brief.md
screenshot.png
expected-nits.yaml
```

The skill compares its nit list to `expected-nits.yaml`. It does **not** stamp UAT.

## Schema (`expected-nits.yaml`)

```yaml
case: T-G01-spelling
brief: brief.md
artifact: screenshot.png
nits:
  - gate: G1          # G1 | G2 | G3 | brief
    class: spelling   # spelling | layout | hex | invented_chrome | invented_logo
    brief_field: cta.label
    where: screenshot.png CTA
    expected: Start campaign
    actual: Start campiagn
    severity: blocker # blocker | major | nit
```

Clean control (`T-A00-clean`) has `nits: []`.

## Cases

| Id | Gate | Expected |
|----|------|----------|
| T-G01-spelling | G1 | misspelled CTA |
| T-G02-layout | G2 | bar hex + CTA x pad vs brief |
| T-G04-overlap | G2 | title vs CTA bbox intersection (`fixtures/T-G04-overlap/`) |
| T-G03-hallucination | G3 | Admin / ACME not in brief (`NOT_IN_BRIEF`) |
| T-A01-wrong-hex | G2 | brand hex mismatch |
| T-A02-1px | G2 | CTA x=23 vs 24 |
| T-A03-invented-logo | G3 | extra wordmark |
| T-A00-clean | — | **zero nits** |

Regenerate PNGs: `powershell -NoProfile -File tools/New-GoldenFixturePngs.ps1`
