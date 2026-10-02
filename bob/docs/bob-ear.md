# Bob ear (fleet box)

Service **ircBob** → `Start-Bob.ps1` → `irc_agent.py`. Nick **`Bob-{MachineId}`**.
Companion: TipForm systray (`scripts\Start-BobTray.ps1` → `tools\Start-BobFleetTray.ps1`).

## Channels and homes

- JOIN `#bobiverse` + `#{MachineId}`
- After Jeeves `!register`: expect **+o** on shop, **+h** on `#bobiverse`
- Home: `<ai root>\bob\home` when ObjectName is LocalSystem; else often `~\.bobiverse`
- Agents: nick `{machine}-{pid}`, JOIN **shop only**

## Secrets

| Secret | Path / env |
|--------|------------|
| Ergo PASS | `<ai root>\bob\config\ergo.password` or `~\.grok\ergo\connect.password` |
| NickServ SASL | `<ai root>\bob\home\nickserv.password` → `BOB_IRC_SASL_USER=bob-{machine}` |
| Service logon | `config\service.password` / `BOBIVERSE_SERVICE_PASSWORD` → DPAPI `service.cred` |
| Digest POST | none (no secret; the digest accepts machine ids on the roster Jeeves publishes) |

Do **not** mint a fresh GUID for an already-registered NickServ account.

## Outbox → airc

UTF-8 **no BOM**. Only lines starting with `PRIVMSG ` are sent raw:

```text
PRIVMSG {machine}_console :<short-cmd>
```

If `<ai root>\bob\home` is LocalSystem-ACL only, interactive users cannot write the outbox — use a talk-seat home.

## Tray / recycle

- Product Sync/ff runs on **ircBob Start-Bob** only — TipForm Start never updates the tree.
- TipForm menu **Restart** → `Restart-BobTrayWatcher` → `Start-BobFleetTray -ForceNew` (restarts `ircBob` via `Restart-BobTrayService`, then relaunches TipForm in the interactive session so Sync/ff runs on ear start).
- Ear-only: Desktop / Start Menu **Restart ircBob** / `scripts\Restart-BobEar.ps1` (announce → `Restart-Service ircBob`).
- Quiet MSI: `Start-BobTrayInteractive.ps1` registers ONLOGON `/IT` task `BobiverseTray` (no session-0 TipForm).
- `!recycle` / `!recycle {machine}`: announce → restart tray + `ircBob`.

## Verify

```powershell
Get-Service ircBob
Get-Content <ai root>\bob\home\irc.log -Tail 40 -ErrorAction SilentlyContinue
# Expect: SASL user=bob-<machine>, joined #bobiverse,#<machine> as Bob-<machine>
```

## Related

- Skill: `.grok/skills/bobiverse-bob/SKILL.md`
- Post-install: `docs/post-install.md`
- Digest curls: `docs/webhooks.md` (hosted on jeeves)
