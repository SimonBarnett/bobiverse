# Functional spec: bobiverse

Pulled from LOCKED vision (`common/docs/vision.md`) + session plan (2026-09-29), enriched from archived gh-Jeeves / bob-design-uat specs (FR #806; archive copies remain under `docs/archive/`).

## Products

1. **jeeves** MSI — Ergo (`BobIrcd`) + chair (`ircJeeves`, nick `Jeeves`).
2. **bob** MSI — ear (`ircBob`, nick `Bob-{machinename}`) + systray + Watch-AgentHealth + icons.
3. **airc** MSI — console (`Airc`, nick `{machinename}_console`).

## Behaviour summary

- Jeeves: `!register <machine>` (Simon/operators); +o all registered channels; `!recycle jeeves` restarts+updates chair; owns `!bored` → assign (ear OFFER retired).
- Bob: JOIN `#bobiverse` + `#wonderland` + `#{machine}` (FR #3835; workers never join `#wonderland`); on JOIN if registered get +o shop / +h bobiverse from Jeeves; listen `!recycle` / `!recycle {mid}`; systray Restart restarts `ircBob` after departure announce.
- airc: JOIN `#{mid}` if registered else `#{domain|workgroup}`.
- Agents: `{machine}-{pid}`, shop only.
- Self-update: GitHub Release MSI on service start (work-tree ff first).
- Skills installed with each MSI for agent maintain/use.
- Intake without GitHub write: `POST /bob/v1/intake` (allow-list live repos only).

## Chair success gate (from archived gh-Jeeves spec, adapted)

**S1 — Token-less end-to-end:** with LLM/token pools disabled, GitHub event → Jeeves announce + queue → worker `!bored` → Jeeves assign → `ACK` → work → `DONE` must complete with scripts only.

- **G1** (CI): local / stub receiver tests; no LLM required on the chair path.
- **G2** (manual after deploy): live smoke on a sandbox repo when the operator records it.

UAT is **per REPO** (`UAT owner/repo#0`) once every non-excluded issue is closed and every PR is merged (t853u). Per-PR UAT rows are not offered.

## Wire grammar (chair / shop)

- Assign: `<nick>: <FR|MRB|UAT> <owner/repo>#<n> <url>`
- Accept: `ACK <TYPE> <owner/repo>#<n>`
- Complete: `DONE <TYPE> <owner/repo>#<n> [PASS|FAIL] <url>`
- Return: `NACK|GIVEUP <TYPE> <owner/repo>#<n>`
- Idle: `!bored` in own `#{machine}` (program-owned for worker seats)
- List: `!list [all|<repo>|fr|mrb|uat]` → PM only

## Visual UAT (from archived bob-design-uat spec)

Live skill path: `bob/.grok/skills/bobiverse-bob-job-uat/` (+ companion `design-uat` guidance). Gates:

| Gate | Check |
|------|--------|
| G1 | OCR / spelling vs brief |
| G2 | Layout / pixel deltas vs brief |
| G3 | Invented chrome/copy not in brief |

Workers report evidence only; they do **not** stamp ready for human UAT (Bob / operator).

## Non-goals

- LLM features on the chair path
- Editing Ergo config / binaries from archive merges
- Filing work against archived superseded repos
