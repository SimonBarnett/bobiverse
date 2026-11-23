# Jeeves admin (Ergo host)

**Chair / Ergo host:** **walrus** (machine id `walrus`). **ionos is deprecated** — do not treat ionos as the live Ergo or `ircJeeves` host.

Chair on the Ergo box: service **ircJeeves**, nick **Jeeves**, tree `<ai root>\jeeves`.
IRCd: **BobIrcd** → live root `<ai root>\ergo` (MSI stages `ergo\` then Install-BobIrcd).

## Checklist

1. Remove legacy **BobJeeves** from SCM (Install-Jeeves does this).
2. Place Ergo connect PASS at `<ai root>\jeeves\config\ergo.password` (public MSIs do not embed it).
3. Set ObjectName to the fleet user via `service.password` / `BOBIVERSE_SERVICE_PASSWORD` / `Complete-BobiverseServiceLogon.ps1 -Product jeeves`.
4. `Restart-Service ircJeeves` — expect `joined #bobiverse,#… as Jeeves`.
   A flat `<ai root>\jeeves` with no `.git` does not pick up `main` on that restart (FR #8493). Use a sparse git worktree or Apply the latest release so chair code such as `heal_false_needs_human_for_infra_soft` is actually on disk.
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

## Skill-dag MCP on the chair install (FR #9136)

Every Jeeves pack/install ships `scripts\skill_dag_mcp.py` (+ `skill_dag_index.py`, `skill_dag_bound.py`) under the install root and writes `<InstallRoot>\.cursor\mcp.json` with a skill-dag stdio server:

- `command` = install python
- `args` = `<InstallRoot>\scripts\skill_dag_mcp.py --root <InstallRoot>\.grok\skills`

Do not borrow `C:\ai\bob\scripts\skill_dag_mcp.py`. After Install/Sync, smoke:

```powershell
python <InstallRoot>\scripts\skill_dag_mcp.py --root <InstallRoot>\.grok\skills --once status
```

Expect `node_count` greater than 0 when skills are present. Monitor refreshes the tracking board, then re-runs `--once status`.

## Related

- Skill: `.grok/skills/bobiverse-jeeves/SKILL.md`
- Webhooks: `docs/webhooks.md`
- Post-install: `docs/post-install.md`

## !build (FR #4006 / #8490 / #8770)

Ops: bare `!build` lists the numbered catalog (digest-home `builds-catalog.json` first, then chair home; HTTP GET `/bob/v1/builds` only when both empty). List rows: name, repo, install, `version=next:Y` (or fixed), ref — each <= 400 bytes; `yml`/`dep`/`output` appear in dry-run. `!build n [version] [ref]` queues a deterministic BUILD from that entry's `yml` path (no agent): suites → pack → export to `output` → reinstall on `install` (machine or `fleet` via `registered-machines.json`). Blank version → next patch of latest numeric `vX.Y.Z[.W]` tag (no tags / tag lookup failure → refuse and ask for an explicit version). Explicit `<version>` must be numeric `x.y.z` or `x.y.z.w` (#4186). Default ref is entry ref or `HEAD`. Bare `!build status` lists running builds; bare `!build cancel` frees all (ops, FR #6715). `!build help` prints the two canonical usage lines. `dep` is documentation only. Old `!build owner/repo` form is refused. Preflight still checks the installed recipe (not a custom catalog path). Use `!build dry-run n` to validate.

## !installtest (FR #4026 WP3)

Ops: `!installtest <owner/repo> <version> [tag]` runs optional INSTALL-TEST from recipe `install_test` (msiexec + post-checks). Use `!installtest dry-run` to validate. Live msiexec on the recipe `install_test.machine` (fold-aware). Failures file `release-blocker` issues via the WP2 filer path.
