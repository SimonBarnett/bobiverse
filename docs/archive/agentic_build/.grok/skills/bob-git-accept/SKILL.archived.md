<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/bob-git-accept/SKILL.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: bob-git-accept
description: >
  Shop backup when Bob is out of Sand: the seat monitor (never the model) says !bored,
  Jeeves assigns the next unaccepted GIT job (one line), worker ACK then
  Start-BobBuild and reports agent+model on the digest webhook.
  Use when the user says !bored, !BORED, git accept, shop idle worker,
  or /bob-git-accept. Queue is the digest report / gh-Jeeves. Do not merge
  until ACK matches. bob-* must not auto-claim.
---

# Shop !bored → Jeeves assigns → ACK → DONE → !bored → …

**CAST IRON (Simon 2026-09-26): after every DONE the process MUST KEEP GOING.**
`!bored` must land on `#{machine}` so Jeeves assigns the next FR|MRB|UAT.
Do not park after one job.

**Preferred:** seat monitor (`Watch-AgentHealth` / AgentMonitor FR #100) posts
`PRIVMSG #{machine} :!bored` within ~5s of DONE (also on start / idle). Never
while a `-p` wake is alive or an ACKed job lacks DONE.

**Continuity:** if the monitor is down or slow, the seat appends
`PRIVMSG #{machine} :!bored` **in the same turn as DONE**. Idle chatter is
still forbidden.

Backup when the builder is out of Sand. `bob-*` does **not** auto-claim
Jeeves `GIT` lines. **Jeeves assigns** on `!bored` (FR #106; ear OFFER
retired). Source of truth: [gh-Jeeves README](https://github.com/SimonBarnett/gh-Jeeves#readme).

The worker does **not** say `!ACCEPT` on this path. It says `ACK` after the
assign line.

## Who speaks

| Nick | Where | What |
|---|---|---|
| `Jeeves` | `#bobiverse` | `GIT …` announce only |
| seat **monitor** (not the model) | shop `#{machine}` only | `!bored` when idle (no -p run, no open ACK) |
| `Jeeves` | that shop | assign: `<nick>: <TYPE> <repo>#<n> <url>` (`!focus` order) |
| same worker | that shop | `ACK <TYPE> <repo>#<n>` → Jeeves marks accepted + busy |
| same worker | — | work; then exact `DONE` line → done + idle |

`!bored` is `PRIVMSG #<shop> :!bored` written by the **monitor** on that
worker's `outbox.txt`. Not the builder outbox. Not `chair-outbox.txt`. Not the LLM.

Legacy `w-<short>-<pid>` nicks are retired for the trust gate; live seats use
`{machine}-{pid}` (for example `marchhare-34992`).

## Queue (digest webhook)

Source of truth for **not-yet-accepted** jobs is the digest report / Jeeves
queue (`queue.json` crash mirror):

`https://irc.ntsa.uk/bob/v1/report`

(`reportUrl` in `config/bobiverse.json`.)

Jeeves owns assign-on-`!bored`, ACK→accepted+busy, DONE→done+idle+supersede.
This skill only describes the **worker** side.

## Worker clock

- Busy (ACK'd job still running): monitor suppresses `!bored`.
- When the job finishes: exact **DONE** line below, then **`!bored`** (monitor
  within ~5s, or seat same-turn if needed). **Keep going.**
- Chair reply on that shop, after `!bored`:
  - `<nick>: nothing queued` — idle continues (monitor will `!bored` again).
  - `<nick>: <TYPE> <repo>#<n> <url>` — **assign**. Reply `ACK <TYPE> <repo>#<n>`
    (FR match rules: ACK FR may match a legacy PR row; see gh-Jeeves FR #102).
- `OFFER`, bare `GIT`, and `#bobiverse` chatter do not start work.
- On one box, the first seat to ACK owns the row. A sibling that sees the same
  assign no-ops.

### AgentMonitor watch seats

Grok/Cursor **watch seats**: `Watch-AgentHealth.ps1` posts `!bored` on start /
after DONE / idle. Continuity: seat may append `PRIVMSG #{machine} :!bored`
right after DONE if the monitor is down. See AgentMonitor FR #100 / #103 and
`docs/feature-request-done-then-bored-keep-going-2026-09-26.md`.

## Start and activity

`Start-BobBuild -Task git` on **this** machine. No `-AllowCopilot`.
Fuel order inside the picker: Cursor Models, then grok-build.

| TYPE | Kind | goal |
|---|---|---|
| `FR` | `build` | issue → implement |
| `MRB` | `mrb` | hostile MRB of `…/pull/{n}` |
| `UAT` | `uat` | Bob stamps only after MRB PASS |

On a real start, POST the digest webhook (`op: merge`) with `working_on`
set to `{agent} {model} {TYPE} {repo}{#n}`, plus `model`, `fuel`, `kind`, and
`repo`. When the job leaves inbox/running, POST `working_on` empty and send
`DONE` (exact wire below).

## DONE wire (exact; CAST IRON)

Jeeves expects one clean DONE line. Prefer exactly:

```text
DONE <MODE> <owner/repo>#<N> [PASS|FAIL] <PR-url>
```

Rules:

- **MODE** = the TYPE **Jeeves assigned** (the word after `<nick>:` on the assign
  line), even if the issue title says MRB or the work became a review.
- **repo#N** = exactly the assigned repo and number.
- At most one optional `PASS` / `FAIL` (or omit for FR with only a URL).
- Then the PR URL (required for FR/MRB when you opened/merged a PR).
- **One DONE line**, starting at column 0, **nothing after the URL**.
- Fix PR numbers, SHAs, companion links, and follow-ups go on a **separate**
  outbox line (or a GitHub comment) — never jammed into DONE.

Examples:

```text
DONE FR SimonBarnett/agentic_build#360 https://github.com/SimonBarnett/agentic_build/pull/363
DONE MRB SimonBarnett/AgentMonitor#112 PASS https://github.com/SimonBarnett/AgentMonitor/pull/112
DONE UAT SimonBarnett/gh-Jeeves#138 PASS
```

Wrong (extra tokens after FAIL before URL; MODE ≠ assign):

```text
DONE MRB SimonBarnett/agentic_fomprep#3 FAIL fix#54 https://github.com/.../pull/54
```

(gh-Jeeves #135 softened parsing of trailing text; workers still use this exact
wire so completions never depend on chair version.)

## Hard rules

- Jeeves **assigns**; workers do not invent OFFER/ASSIGN lines.
- ACK before work; DONE after work (exact wire, assigned MODE); then **`!bored`**
  so the next job arrives (CAST IRON keep-going).
- Prefer monitor `!bored`; seat may post `PRIVMSG #{machine} :!bored` after DONE
  for continuity when the monitor lags.
- Self-MRB only when one live seat (CAST IRON).
- Do not merge UNSTABLE.
