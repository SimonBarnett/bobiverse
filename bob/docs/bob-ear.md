# Bob ear (fleet box)

Service **ircBob** -> `Start-Bob.ps1` -> **`scripts\bob-ear.exe`** (FR #1481, self-contained frozen `irc_agent`) or, on repo/dev trees without the exe, `python -u irc_agent.py`. Nick **`Bob-{MachineId}`**.
Companion: TipForm systray (`scripts\Start-BobTray.ps1` -> `tools\Start-BobFleetTray.ps1`).

Build/pack: `scripts\Build-BobEar.ps1` (PyInstaller) -> staged by `Pack-BobiverseRelease` into the bob MSI. Safe swap: `scripts\Install-BobEarExe.ps1` (keeps `bob-ear.exe.bak`, restores on smoke failure).

## Channels and homes

- JOIN `#bobiverse` + `#{MachineId}` (identical `Start-Bob` `--channel #bobiverse,#<machine>` on every box — Ionos host, MarchHare, Flamingo, …)
- **DIGEST_ID_FOLD (harvest #2280 / PR #2279):** digest aliases fold to the real shop id — `ionos` -> `win-mpre8vi4u6u`, `dev1` -> `ce-priority-dev1`. Helpers (`inbound_transcript.channel_list_for_machine` / `canonical_machine_id`) must never emit `#ionos` or `#dev1` as the shop channel.
- After Jeeves `!register`: expect **+o** on shop, **+h** on `#bobiverse`
- Home: `<ai root>\bob\home` when ObjectName is LocalSystem; else often `~\.bobiverse`
- **`--home` isolation (FR #2350):** an explicit scratch `--home` (UAT under `%TEMP%`, …) does **not** merge `~\.agentic-irc-bobiverse`. Fleet basenames `home` / `.bobiverse` still one-time migrate. Opt-in: `BOB_MIGRATE_LEGACY=1`. Opt-out: `BOB_HOME_NO_MIGRATE=1`.
- Agents: nick `{machine}-{pid}`, JOIN **shop only**

## Listen (inbound transcript) — FR #2174

Every running ear always appends scrubbed inbound PRIVMSG lines to:

```text
<bob home>\inbound-transcript.log
```

Each line is `UTC-timestamp channel nick text` (secrets redacted). The file rotates by size (`inbound-transcript.log.1` …). This is **always on** — it does not need `BOB_IRC_DEBUG`. Raw wire dump (`irc.log`) remains opt-in via `BOB_IRC_DEBUG=1`.

Workers still only inject lines **FROM Jeeves** addressed to that seat (`bob_worker.accept_for_agent`); other PRIVMSG stay in the transcript for Shell/operators.

## Secrets

| Secret | Path / env |
|--------|------------|
| Ergo PASS | `<ai root>\bob\config\ergo.password` or `~\.grok\ergo\connect.password` |
| NickServ SASL | `<ai root>\bob\home\nickserv.password` -> `BOB_IRC_SASL_USER=bob-{machine}` |
| Service logon | `config\service.password` / `BOBIVERSE_SERVICE_PASSWORD` -> DPAPI `service.cred` |
| Digest POST | none (no secret; the digest accepts machine ids on the roster Jeeves publishes) |

Do **not** mint a fresh GUID for an already-registered NickServ account.

## Outbox (send) — identical on every machine

UTF-8 **no BOM**. Append one complete line per send to `<bob home>\outbox.txt`. Only lines starting with `PRIVMSG ` are sent raw (same interface on Ionos / MarchHare / Flamingo):

```text
PRIVMSG <target> :<text>
PRIVMSG #<machine> :<shop line>
PRIVMSG #bobiverse :!help
PRIVMSG {machine}_console :<short-cmd>
```

Offset is tracked in `outbox.txt.pos`; up to 8 lines drain per tick. If `<ai root>\bob\home` is LocalSystem-ACL only, interactive users cannot write the outbox — use a talk-seat / worker run home for agent replies.

## Absent / stale ear recovery

| State | Action |
|-------|--------|
| No `ircBob` / service Stopped | `Install-Bob.ps1` (or MSI) then `Start-Service ircBob` |
| Leftover `irc_listen.py` only (Flamingo-style) | Retire it; install/start `ircBob` ear above |
| Running but no `inbound-transcript.log` | `Restart-BobEar.ps1` after this FR is deployed |
| Missing `outbox.txt` | Ear recreates home on start; ensure service ObjectName/home path |

## Tray / recycle

- Product Sync/ff runs on **ircBob Start-Bob** only — TipForm Start never updates the tree.
- TipForm menu **Restart** -> `Restart-BobTrayWatcher` -> `Start-BobFleetTray -ForceNew` (restarts `ircBob` via `Restart-BobTrayService`, then relaunches TipForm in the interactive session so Sync/ff runs on ear start).
- Ear-only: Desktop / Start Menu **Restart ircBob** / `scripts\Restart-BobEar.ps1` (announce -> `Restart-Service ircBob`).
- Quiet MSI: `Start-BobTrayInteractive.ps1` registers ONLOGON `/IT` task `BobiverseTray` (no session-0 TipForm).
- `!recycle` / `!recycle {machine}`: announce -> restart tray + `ircBob`.

## Verify

```powershell
Get-Service ircBob
Get-Content <ai root>\bob\home\inbound-transcript.log -Tail 40 -ErrorAction SilentlyContinue
Get-Content <ai root>\bob\home\irc.log -Tail 40 -ErrorAction SilentlyContinue  # only when BOB_IRC_DEBUG=1
# Expect: SASL user=bob-<machine>, joined #bobiverse,#<machine> as Bob-<machine>
# Expect: inbound-transcript.log lines like: 2026-10-04T12:00:00Z #marchhare Jeeves …
```

## Related

- Skill: `.grok/skills/bobiverse-bob/SKILL.md`
- Post-install: `docs/post-install.md`
- Digest curls: `docs/webhooks.md` (hosted on jeeves)
