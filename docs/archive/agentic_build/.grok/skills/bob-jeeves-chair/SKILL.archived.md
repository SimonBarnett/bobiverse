<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/bob-jeeves-chair/SKILL.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: bob-jeeves-chair
description: >
  Digest chair Jeeves on ionos: Windows service BobJeeves (canonical install in
  SimonBarnett/gh-Jeeves), homes, !recycle, and GIT outbox. Use when the user
  says Jeeves, chairNick, BobJeeves, digest chair, !recycle, GIT outbox,
  BOB_DIGEST_HOME, or /bob-jeeves-chair. Wire join/firewall stays agentic_irc
  bob-irc. Digest shape is bob-digest-webhook. Builders are not the chair.
---

# Jeeves (digest chair)

`!bobiverse` answers and `BOB DIGEST v1` whispers come from **Jeeves**, not
from `bob-ionos` / `bob-flamingo` / `bob-marchhare` / `bob-dev1`.

## Canonical product (FR agentic_build#330 → gh-Jeeves)

**Production chair is [SimonBarnett/gh-Jeeves](https://github.com/SimonBarnett/gh-Jeeves).**
Install / recycle with that repo's `tools/Install-BobJeeves.ps1` (`python -m jeeves`,
combined chair+receiver, Automatic start, failure restart, disables
`BobJeeves-chair` task). Headline acceptance: **token-less** GIT → announce →
queue → `!bored` assign → ACK → DONE → supersede (gh-Jeeves FR #1 / G1 e2e).

This agentic_build tree still ships a **legacy** NSSM + `agentic_irc` wrapper
(`tools/Install-BobJeeves.ps1` / `Start-BobJeeves.ps1`) for older ionos boxes.
Do not treat that as the FR #330 success path. Prefer sibling `C:\ai\gh-Jeeves`
or `D:\ai\gh-Jeeves`.

## Identity

| | |
|---|---|
| Nick | `Jeeves` (exactly one; never `Jeeves_`) |
| Machine | ionos chair home |
| Install (canonical) | `gh-Jeeves/tools/Install-BobJeeves.ps1 -Apply -Production` |
| Install (legacy) | `agentic_build/tools/Install-BobJeeves.ps1` (NSSM, depends on BobIrcd) |
| Not the builder | `Watch-Bobiverse` must not become the chair. |

Live chair nick is **Jeeves**. Do not start a second chair.

## Auto-start

Windows service **`BobJeeves`** (Automatic). Do not start Jeeves from a grok.exe
reasoning loop. Do not re-create from scheduled task `BobJeeves-chair` (removed
on install).

| Need | Action |
|---|---|
| Ergo / IRC down | Fix **BobIrcd** first (`Start-Service BobIrcd` / cert scripts). gh-Jeeves service does **not** SCM-depend on BobIrcd; still needs Ergo up to join. |
| Chair down, IRC up | `Restart-Service BobJeeves` only. |
| Cert renewal | `Install-BobIrcdCert.ps1` restarts BobIrcd; then confirm BobJeeves. |
| Old task | Do not `Start-ScheduledTask BobJeeves-chair` / `BobIrcd-ionos`. |

Do not `Stop-Process ergo`. Do not copy NSSM from another product.
## Homes (do not merge them)

| Home | What it is |
|---|---|
| `--home` / `BOB_IRC_HOME` / `AGENTIC_IRC_HOME` | IRC client home for **that seat**. Builders: `~\.agentic-irc-bobiverse`. `irc_agent.py --home` must be that seat's home. |
| `BOB_DIGEST_HOME` | Digest chair files (Jeeves publish/consume, chair outbox). Separate from a builder `--home`. |

Do not point a `bob-*` `--home` at the digest home. Do not let Jeeves share `bob-ionos` `outbox.txt`. If `BOB_DIGEST_HOME` is unset, read it from the `BobJeeves` service environment. Do not guess a path.

Builder recycle does not use this split as an excuse to restart Ergo. See `bob-irc`: Watch-Bobiverse only.

## GIT outbox

GitHub delivers to `https://irc.ntsa.uk/bob/v1/git` (`setup-github-webhooks`). Jeeves announces accepted events as `GIT ...` on `#bobiverse` from **its** outbox. `bob-*` and talk seats do not narrate GIT. Announce text: agentic_irc skill `jeeves-git-webhook`. A create/ping is `GIT ping`.

Digest merges go to `/bob/v1/report`, not `/bob/v1/git`.

## `!bored` → assign (FR #106)

In every `#{machine}`, a trusted `{machine}-<pid>` worker says `!bored`.
**Jeeves assigns** the next job (`<nick>: <TYPE> <repo>#<n> <url>`, `!focus`
order). ACK → accepted + busy; DONE → done + idle + supersede. The ear OFFER
path is retired. Worker pack: `bob-git-accept`. Source of truth:
[gh-Jeeves README](https://github.com/SimonBarnett/gh-Jeeves#readme).

## !recycle

Jeeves is the ionos notify path for `!recycle`. Implementer PR workers do **not** send live `!recycle` (`bob-hostile-mrb`). Bob or the merger on ionos runs recycle after merge to main.

| Change | Recycle |
|---|---|
| TipForm / tray paint | Kill all `Watch-BobTray`, one CreateNoWindow start (`bob-fleet-tray`). Not Jeeves. |
| Builder IRC peer loop | `Watch-Bobiverse` only (`bob-irc`). Not `BobIrcd`. |
| Ergo / cert / chair code | `Restart-Service BobIrcd` and, if the chair changed, `Restart-Service BobJeeves`. |
| Fleet jobs still running | Do not `Stop-ScheduledTask BobFleet-*`. |

## Hard rules

- One chair nick: Jeeves.
- BobJeeves depends on BobIrcd. Do not recycle Ergo for a tray paint change.
- Do not print `connect.password`, `report.secret`, or `X-Bob-Secret`.
- Canonical IRC wire (JOIN, firewall, Halloy): agentic_irc `.grok/skills/bob-irc`. This file is the chair contract for agentic_build.
