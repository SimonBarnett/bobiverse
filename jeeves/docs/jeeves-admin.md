# Jeeves admin (Ergo host)

Chair on the Ergo box: service **ircJeeves**, nick **Jeeves**, tree `<ai root>\jeeves`.
IRCd: **BobIrcd** → live root `<ai root>\ergo` (MSI stages `ergo\` then Install-BobIrcd).

## Checklist

1. Remove legacy **BobJeeves** from SCM (Install-Jeeves does this).
2. Place Ergo connect PASS at `<ai root>\jeeves\config\ergo.password` (public MSIs do not embed it).
3. Set ObjectName to the fleet user via `service.password` / `BOBIVERSE_SERVICE_PASSWORD` / `Complete-BobiverseServiceLogon.ps1 -Product jeeves`.
4. `Restart-Service ircJeeves` — expect `joined #bobiverse,#… as Jeeves`.
5. Wire git webhooks to `https://bob.ntsa.uk/bob/v1/git` (see `docs/webhooks.md`).

## Homes

| Role | Path |
|------|------|
| Chair | `~\.jeeves` (prefer Admin on Ergo host; else `<ai root>\jeeves\home-jeeves`) |
| Digest | `BOB_DIGEST_HOME=~\.bobiverse` |
| Logs | `<ai root>\jeeves\logs\stdout.log`, `stderr.log` |

Quiet MSI as LocalSystem must **not** bake `C:\Users\Default\.jeeves` into NSSM.

Home migration (`bob_home.migrate_legacy`) copies legacy `~\.agentic-irc-*` into `~\.jeeves` / `~\.bobiverse` once. Live `*.pos` files are skipped with other process state, but **outbox cursors are sealed** (FR #68): after copying `chair-outbox.txt` / `outbox.txt`, the migrator restores `*.pos` from the old home when present, otherwise writes pos = file size so the chair does not replay thousands of old GIT lines and starve `SAMODE` / ChanServ LIST. The outbox drain also caps lines per tick and runs ChanServ/+o before drain.

## Operator commands (IRC)

- `!register <machine>` — ChanServ REGISTER `#{machine}` (+o/+h in #bobiverse; FR #4008)
- `!unregister <machine>` — inverse: ChanServ UNREGISTER, drop roster, PART shop (+o/+h; confirm/dry-run; FR #4008)
- `!recycle jeeves` — restart `ircJeeves` only (not BobIrcd)
- `!recycle <machine>`, `!list`, digest / GIT / chair-outbox — existing chair surface

## DPAPI pitfall

Admin-sealed `identity.json` under LocalSystem → `CryptUnprotectData failed`. Prefer fixing ObjectName. Interim: park as `identity.json.admin-dpapi.bak` so LocalSystem mints a fresh identity (SEAL key changes).

## Related

- Skill: `.grok/skills/bobiverse-jeeves/SKILL.md`
- Webhooks: `docs/webhooks.md`
- Post-install: `docs/post-install.md`

## !build (FR #4006)

Ops: `!build <owner/repo> <version> [ref]` queues a deterministic BUILD from `.bobiverse/build.yml` (no agent). `<version>` must be numeric `x.y.z` or `x.y.z.w` (digits only); `v0.1.32` / `0.1.32-test2` are refused (#4186). Use `!build dry-run` to validate. Live pack/suites: WP2 on the recipe `machine`.

## !installtest (FR #4026 WP3)

Ops: `!installtest <owner/repo> <version> [tag]` runs optional INSTALL-TEST from recipe `install_test` (msiexec + post-checks). Use `!installtest dry-run` to validate. Live msiexec on the recipe `install_test.machine` (fold-aware). Failures file `release-blocker` issues via the WP2 filer path.
