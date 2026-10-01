# Bob ear (fleet box)

Service **ircBob** → `Start-Bob.ps1` → `irc_agent.py`. Nick **`Bob-{MachineId}`**.
Companion: TipForm systray (`scripts\Start-BobTray.ps1` → `tools\Start-BobFleetTray.ps1`).

## Channels and homes

- JOIN `#bobiverse` + `#{MachineId}`
- After Jeeves `!register`: expect **+o** on shop, **+h** on `#bobiverse`
- Home: `C:\ai\bob\home` when ObjectName is LocalSystem; else often `~\.bobiverse`
- Agents: nick `{machine}-{pid}`, JOIN **shop only**

## Secrets

| Secret | Path / env |
|--------|------------|
| Ergo PASS | `C:\ai\bob\config\ergo.password` or `~\.grok\ergo\connect.password` |
| NickServ SASL | `C:\ai\bob\home\nickserv.password` → `BOB_IRC_SASL_USER=bob-{machine}` |
| Service logon | `config\service.password` / `BOBIVERSE_SERVICE_PASSWORD` → DPAPI `service.cred` |
| Digest POST | `BOB_REPORT_SECRET` or `~\.grok\bob\report.secret` |

Do **not** mint a fresh GUID for an already-registered NickServ account.

## Outbox → airc

UTF-8 **no BOM**. Only lines starting with `PRIVMSG ` are sent raw:

```text
PRIVMSG {machine}_console :<short-cmd>
```

If `C:\ai\bob\home` is LocalSystem-ACL only, interactive users cannot write the outbox — use a talk-seat home.

## Tray / recycle

- Product Sync/ff runs on **ircBob Start-Bob** only — TipForm Start never updates the tree.
- TipForm **Restart ircBob** → `Restart-BobEar` (service recycle → Start-Bob Sync/ff) then relaunches TipForm in the interactive session.
- Desktop **Bob Fleet Restart** / `Restart-BobEar.ps1` is the same service recycle path.
- Quiet MSI: `Start-BobTrayInteractive.ps1` registers ONLOGON `/IT` task `BobiverseTray` (no session-0 TipForm).
- `!recycle` / `!recycle {machine}`: announce → restart tray + `ircBob`.

## Verify

```powershell
Get-Service ircBob
Get-Content C:\ai\bob\home\irc.log -Tail 40 -ErrorAction SilentlyContinue
# Expect: SASL user=bob-<machine>, joined #bobiverse,#<machine> as Bob-<machine>
```

## Related

- Skill: `.grok/skills/bobiverse-bob/SKILL.md`
- Post-install: `docs/post-install.md`
- Digest curls: `docs/webhooks.md` (hosted on jeeves)
