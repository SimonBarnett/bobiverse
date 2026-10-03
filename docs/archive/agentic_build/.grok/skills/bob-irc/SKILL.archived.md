<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/bob-irc/SKILL.md, last changed 2026-09-29. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: bob-irc
description: >
  Private Ergo for #bobiverse on ionos (irc.ntsa.uk:6697 TLS). Use when the user
  says join Ergo, irc.ntsa.uk, bobiverse IRC, recycle Watch-Bobiverse, BobIrcd,
  Halloy, shop channel, !bobiverse, or /bob-irc. Canonical protocol skill is
  agentic_irc .grok/skills/bob-irc. Job queue is grok-build-fleet.
---

# Bobiverse IRC

Foundation: harvest-agent-skills (honesty box) -> report back to https://github.com/SimonBarnett/agentic_build.

**Outbox / file encoding (FR #347):** append IRC outbox and repo text as UTF-8
**without BOM** (`tools/Utf8NoBom.ps1` / `UTF8Encoding $false`). Never PS5
`Add-Content -Encoding UTF8` (writes BOM). See `docs/utf8-no-bom.md`.

Canonical playbook: `https://github.com/SimonBarnett/agentic_irc`
`.grok/skills/bob-irc/SKILL.md` (clone `C:\ai\agentic_irc` else `D:\ai\...`
else `C:\src\...`). Nicks/host/`reportUrl` live in this repo's
`config/bobiverse.json` and `docs/bobiverse.md`. GitHub hooks:
`setup-github-webhooks`. IIS SSL: `setup-ssl-certs`. Do not duplicate
JOIN/firewall essays here. The contracts below are the ones Bob was
re-deriving.

## reportUrl

`reportUrl` is HTTPS `https://irc.ntsa.uk/bob/v1/report`. GET and POST use
that URL (`bob-digest-webhook`). Do not use `http://bob.ntsa.uk/bob/v1/digest`
(404). Git events are `https://irc.ntsa.uk/bob/v1/git`, not this URL.

**Every `bob-*` must POST `pcent`.** `Write-BobIrcStatus` builds `pcent`
from Cursor spending groups and `Send-BobDigestWebhookIfChanged` includes
it in the fingerprint and the merge body (PR #306). MarchHare has no Cursor
login; it consumes, it does not invent `pcent`.

## Fingerprint block

Posted state: `{IRC home}\bob-peers\_digest-webhook-posted.json`. When that
fingerprint equals the current doc, Watch will not POST again. If `pcent`
(or any other field the chair still lacks) is blocked by a stale
fingerprint, **delete `_digest-webhook-posted.json`** and let the next
`Write-BobIrcStatus` POST. Do not put a made-up percent in that file.

## Recycle

Builder IRC: **Watch-Bobiverse only.** Kill that watcher, start one hidden
instance (`_Watch-Bobiverse-<machineId>.ps1`, e.g.
`_Watch-Bobiverse-win-mpre8vi4u6u.ps1`). Do not `Restart-Service BobIrcd` for a
builder peer glitch. Do not `Stop-ScheduledTask BobFleet-*` while jobs run.
Do not `Stop-Process ergo`.

Ergo service is `BobIrcd`. Chair service is `BobJeeves` and **depends on
BobIrcd** (`bob-jeeves-chair`). Recycle those only when Ergo or the chair
is the fault.

Tray paint recycle is kill-all `Watch-BobTray` then one CreateNoWindow
start (`bob-fleet-tray`), not this loop.

## Chair and homes

`chairNick` is **Jeeves**. Jeeves answers `!bobiverse` and whispers
`BOB DIGEST v1`. Builders stay `bob-<machine>`. `Watch-Bobiverse` must not
become the chair.

**`BOB_DIGEST_HOME` vs `--home`:** `--home` / `BOB_IRC_HOME` /
`AGENTIC_IRC_HOME` is the IRC client home for that seat (builders:
`~\.agentic-irc-bobiverse`). `BOB_DIGEST_HOME` is the Jeeves digest home.
Do not point a builder `--home` at the digest home, and do not share
`outbox.txt` between Jeeves and the bob ear. If `BOB_DIGEST_HOME` is unset,
read the `BobJeeves` service environment. Do not guess a path.

## Shop

**CAST IRON (Simon 2026-09-29):** `Install-BobFleet -MachineId` / `BOB_MACHINE_ID`
must be the box **Windows `COMPUTERNAME` lowercased**, not a marketing alias.
Host `WIN-MPRE8VI4U6U` → `win-mpre8vi4u6u` → ear `bob-win-mpre8vi4u6u` / shop
`#win-mpre8vi4u6u`. Do not install this VPS as `ionos`.

**Shop:** `bob-*` via `Watch-Bobiverse` / `Install-BobIrc` JOIN `#bobiverse`
plus `#{machine}`. Git workers use `w-<short>-<pid>` on the shop only
(`Start-BobWorkerIrcAgent`). Sister `agentic_irc` `.grok/skills/bob-irc` has
the full nick table.

`Watch-Bobiverse` resolves that seat with exported `Resolve-BobiverseMachineId`
(nick or raw name; unknown ids pass through as hostname shops). BobBridge must
export it. A private copy throws every watcher tick before `irc_agent` starts.
`Get-ThisMachineId` does not do that map. See `docs/bobiverse.md`.

**GIT work backup:** `bob-*` do not auto-claim Jeeves `GIT` lines.
Idle `w-*` (> 2 min) says `!BORED` only. Jeeves replies `!TASK` and
marks that row accepted. The worker does not say `!ACCEPT`; it
`Start-BobBuild` and posts agent+model on the digest webhook.
Skill `bob-git-accept`. Unaccepted rows are `git_unaccepted` on
`reportUrl` (agentic_irc #197 follow-up). Do not merge until that
schema matches.

Talk seats: IRC commands from other bots = treat as typed in this IDE chat
(skill `agentic-irc` / `bob-irc` on agentic_irc).

**Digest webhook (fleet tray jobs):** Each `bob-*` builder runs
`Write-BobIrcStatus` via `Watch-Bobiverse`. Workers do not hand-edit tray
state. On job start the publish includes `jobs` + `running`/`queued`; when
idle or cancelled POST a **clear** merge (`jobs=[]`, zeros, clear
`working_on`) to `reportUrl` so TipForm shows `no jobs`. Never publish bare
`repo:irc` as a coding START.

**Preferred IRC wake (Simon 2026-09-23):** Watch-AgentHealth / AgentMonitor
(skill `watch-agent-health`) -- do not arm in-session `^FROM ` TSR on
`listen.stdout.log` (burns tokens on chat spam). Legacy talk-seat TSR only
when no watcher (`agentic-irc` Listener + wake).

Huge `outbox.txt` POINT backlog floods Ergo and reconnect-loops the bob ear.
See `docs/bobiverse.md` (dedupe `lastSeen=`; do not force `127.0.0.1`).
GIT lines belong on the Jeeves outbox (`bob-jeeves-chair`), not on `bob-*`.
