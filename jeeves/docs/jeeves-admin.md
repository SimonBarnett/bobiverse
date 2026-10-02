# Jeeves admin (Ergo host)

Chair on the Ergo box: service **ircJeeves**, nick **Jeeves**, tree `<ai root>\jeeves`.
IRCd: **BobIrcd** → live root `<ai root>\ergo` (MSI stages `ergo\` then Install-BobIrcd).

## Checklist

1. Remove legacy **BobJeeves** from SCM (Install-Jeeves does this).
2. Place Ergo connect PASS at `<ai root>\jeeves\config\ergo.password` (public MSIs do not embed it).
3. Set ObjectName to the fleet user via `service.password` / `BOBIVERSE_SERVICE_PASSWORD` / `Complete-BobiverseServiceLogon.ps1 -Product jeeves`.
4. `Restart-Service ircJeeves` — expect `joined #bobiverse,#… as Jeeves`.
5. Wire git webhooks to `https://irc.ntsa.uk/bob/v1/git` (see `docs/webhooks.md`).

## Homes

| Role | Path |
|------|------|
| Chair | `~\.jeeves` (prefer Admin on Ergo host; else `<ai root>\jeeves\home-jeeves`) |
| Digest | `BOB_DIGEST_HOME=~\.bobiverse` |
| Logs | `<ai root>\jeeves\logs\stdout.log`, `stderr.log` |

Quiet MSI as LocalSystem must **not** bake `C:\Users\Default\.jeeves` into NSSM.

Home migration (`bob_home.migrate_legacy`) copies legacy `~\.agentic-irc-*` into `~\.jeeves` / `~\.bobiverse` once. Live `*.pos` files are skipped with other process state, but **outbox cursors are sealed** (FR #68): after copying `chair-outbox.txt` / `outbox.txt`, the migrator restores `*.pos` from the old home when present, otherwise writes pos = file size so the chair does not replay thousands of old GIT lines and starve `SAMODE` / ChanServ LIST. The outbox drain also caps lines per tick and runs ChanServ/+o before drain.

## Operator commands (IRC)

- `!register <machine>` — ChanServ REGISTER `#{machine}` (Simon/operators)
- `!recycle jeeves` — restart `ircJeeves` only (not BobIrcd)
- `!recycle <machine>`, `!list`, digest / GIT / chair-outbox — existing chair surface

## DPAPI pitfall

Admin-sealed `identity.json` under LocalSystem → `CryptUnprotectData failed`. Prefer fixing ObjectName. Interim: park as `identity.json.admin-dpapi.bak` so LocalSystem mints a fresh identity (SEAL key changes).

## Related

- Skill: `.grok/skills/bobiverse-jeeves/SKILL.md`
- Webhooks: `docs/webhooks.md`
- Post-install: `docs/post-install.md`
