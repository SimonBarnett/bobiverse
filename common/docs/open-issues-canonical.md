# Open issues canonical map (FR #602)

Housekeeping snapshot after clearing ~200 duplicate intake/harvest/CRITICAL re-offer issues on 2026-10-03.
Duplicates were **closed** (never deleted) with a comment pointing at the canonical issue below.

## Protected / leave alone (per FR #602)

| Issue | Why |
|------:|-----|
| [#118](https://github.com/SimonBarnett/bobiverse/issues/118) | ionos-only chair GIT announce |
| [#153](https://github.com/SimonBarnett/bobiverse/issues/153) | needs Simon (tray ONLOGON) |
| [#161](https://github.com/SimonBarnett/bobiverse/issues/161) | release gate (bob-worker GIVEUP/NACK busy) |
| [#232](https://github.com/SimonBarnett/bobiverse/issues/232) | release gate (ship bob-worker.exe pack for #161) |

## Canonicals (one per topic)

| Topic | Canonical | Notes |
|-------|----------:|-------|
| agentic_fomprep#3 mrb-home / needs_human | [#298](https://github.com/SimonBarnett/bobiverse/issues/298) | Related skip shipped in PR [#271](https://github.com/SimonBarnett/bobiverse/pull/271); ionos drain still human |
| agentic_fomprep#7 umbrella labels | [#287](https://github.com/SimonBarnett/bobiverse/issues/287) | Label umbrella/parent-fr/mrb-home on fomprep#7 |
| agentic_fomprep#8 umbrella labels | [#296](https://github.com/SimonBarnett/bobiverse/issues/296) | Label umbrella/parent-fr/mrb-home on fomprep#8 |
| Skip mrb / mrb-fail / mrb-pass verdict boards from FR enqueue | [#315](https://github.com/SimonBarnett/bobiverse/issues/315) | Covers fomprep#9/#11/#20 class |
| Fake MRB `/pull/{issue_id}` | [#247](https://github.com/SimonBarnett/bobiverse/issues/247) | Implementer work on gh-Jeeves#229; harden umbrella [#595](https://github.com/SimonBarnett/bobiverse/issues/595) |
| UAT author_seat / self-UAT | [#265](https://github.com/SimonBarnett/bobiverse/issues/265) | Also covers MRB-seat self-UAT |
| Self-MRB to implementer seat | [#593](https://github.com/SimonBarnett/bobiverse/issues/593) | |
| require_machine for WP0 live (ce-priority-dev1) | [#587](https://github.com/SimonBarnett/bobiverse/issues/587) | |
| Harden MRB/FR routing (fake pull + verdict skip) | [#595](https://github.com/SimonBarnett/bobiverse/issues/595) | Implementer PR [#603](https://github.com/SimonBarnett/bobiverse/pull/603) (open) |
| Install flat scripts lag after ff | [#269](https://github.com/SimonBarnett/bobiverse/issues/269) | |
| Intake allow-list agentic_fomprep | [#285](https://github.com/SimonBarnett/bobiverse/issues/285) | |
| Re-queue MRB on already-merged MRB-fix | [#224](https://github.com/SimonBarnett/bobiverse/issues/224) | |
| UAT #271 live ionos compose/recycle | [#610](https://github.com/SimonBarnett/bobiverse/issues/610) | Post-snapshot; related [#269](https://github.com/SimonBarnett/bobiverse/issues/269) [#298](https://github.com/SimonBarnett/bobiverse/issues/298) |
| Intake webhook 400 on gap filing | [#611](https://github.com/SimonBarnett/bobiverse/issues/611) | Post-snapshot |

## Already fixed (closed as done / duplicate during #602)

- FR #238 airc encoding → PR #273 + #598
- FR #254 DONE-FR supersede → PR #275 + #589
- FR #258 mrb-home skip → PR #271
- Issue #39 chair focus/ACK gaps → PR #49

## Policy for new intake

Prefer commenting on the canonical issue (or a single CRITICAL once) over opening a new harvest/CRITICAL for every repeated GIVEUP on the same board.