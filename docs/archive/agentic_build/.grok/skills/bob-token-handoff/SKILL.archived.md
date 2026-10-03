<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/bob-token-handoff/SKILL.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: bob-token-handoff
description: >
  Token-efficient fleet dispatch: read the live digest webhook first, then
  pick fuel and code-agent tier. Use when the user says fuel, which model,
  cursor-models remaining, handoff, cheap agent, free agent, PR low, MRB
  medium, UAT high, never Other Models, or /bob-token-handoff. Launch:
  start-bob-cursor / start-bob-copilot. Loop: bob-job-loop. Digest:
  bob-digest-webhook. Do not invent usage numbers.
---

# Token handoff

Bob listens and assigns fleet work (fuel + machine). Shop job claim is
separate: **Jeeves assigns** on worker `!bored` (gh-Jeeves FR #106 / K10;
gh-Jeeves README is SoT). Bob does not implement the PR and does not write
the MRB. Follow this order. Do not re-reason it from chat memory.

## 1. Fuel number from the live digest

GET `https://irc.ntsa.uk/bob/v1/report` (`bob-digest-webhook` checklist).
Use `pcent.cursor-models` (auto / low cost models remaining).

- Missing key: unknown. Do not invent `0` and do not invent a positive percent.
- `0`: included Cursor Models are empty. Fall through.
- Greater than `0`: fuel `cursor-models`.
- MarchHare has no Cursor login. Do not read a local Cursor file on MarchHare as the fuel number. Use the digest (peers that have a login publish `pcent`).
- If the digest GET fails, on a host that **does** have a Cursor login run `Get-BobCursorAgentWeeklyRemaining` (`box-usage`). Still do not invent the figure.
- Sand / `grok-chat` at 100% does not mean auto is empty. On-demand GBP is not the fuel remaining figure.

## 2. Fuel order

`Get-BobFuelOrder` / `Select-BobGitWorker`:

1. `cursor-models` while digest (or local, when trusted) remaining is greater than 0.
2. Else `grok-build` (grok.exe).
3. `copilot` only when the operator passed `-AllowCopilot` (CCA is often off).
4. `grok-bot` after that.
5. `on-demand` only with `-AllowOnDemand`.

**Never Other Models.** That spending group is the high cost models meter, not a worker fuel.

Maximize free and cheap agents when they are available: included `cursor-models` before grok.exe; inside Cursor, the low tier below before a higher model. Idle git-eligible machine with zero jobs wins (`Select-BobGitWorker`). DUMB / 2012 is not a git worker. Ids: `ionos`, `marchhare`, `dev1`, `flamingo`.

## 3. Code-agent tier

| Work | Tier | Model |
|---|---|---|
| PR / `-Kind build` | low | cursor-models: Composer `composer-2.5` (`models.buildCursor`). grok.exe: `build0.1` if `grok models` lists it, else `grok-4.5` (`Resolve-BobGrokCliModel`, `buildGrokFallback`). |
| MRB / `-Kind mrb` | medium | `grok-4.6` (`models.mrbCursor` on cursor-agent, `models.mrbGrok` on grok.exe). New worker. Never the implementer. |
| UAT | high | Bob assigns only. Bob stamps ready for human UAT. Do not spend a high code agent to implement or to MRB. Workers do not stamp UAT. |

Confirm `--model` on the live process when fuel is cursor-models (`start-bob-cursor`).

## 4. Assign, then stop

Dispatcher: `bob-build-dispatch` then `bob-job-loop` (`Start-BobBuildLoop.ps1`). Launch the driver. Do not sit in the MRB table. Do not retype `Start-BobMrbHandoff` unless the driver cannot start.

Cursor start miss or remaining 0: grok-build fallback. Re-read the digest at each start (the loop already re-reads fuel; the number source is this skill).

## Hard rules

- Do not invent usage numbers.
- Never Other Models.
- Bob listens and assigns only.
- Copilot is not the default when `cursor-models` remaining is greater than 0.
