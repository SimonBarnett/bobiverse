<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/bobiverse-ionos-ircd.md, last changed 2026-09-29. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Ionos Ergo — `#ionos` shop channel

**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/70  
**Sister cross-link:** add one row to `agentic_build/docs/bobiverse.md` shop table:
`ionos` → `#ionos`, builder `bob-ionos`, workers `w-io-<pid>` (no UAT stamp here).

## Operator facts

- Private Ergo on ionos: TLS `irc.ntsa.uk:6697` only (not Libera).
- Fleet room `#bobiverse` and shop `#ionos` must both accept registered fleet nicks.
- **`bob-ionos`** JOINs **`#bobiverse`** and **`#ionos`** on every connect/reconnect
  (Watch-Bobiverse → `scripts/irc_agent.py` sends one `JOIN` per channel).
- Git workers on ionos: nick `w-io-<pid>`, home
  `~\.agentic-irc-bobiverse\workers\ionos\<pid>`, shop **`#ionos` only**.

## Verify after Watch recycle

In `~\.agentic-irc-bobiverse\irc.log` (with `AGENTIC_IRC_DEBUG=1`) or Ergo logs,
same session should show:

```
JOIN #bobiverse
JOIN #ionos
```

(and matching JOIN echoes for `bob-ionos`).

## Service recovery

Windows service **`BobIrcd`** (`Start-Service BobIrcd`). Do not use the removed
`BobIrcd-ionos` scheduled task. See skill `bob-irc`.

## ChanServ — REGISTER `#ionos` (FR #313)

Shop channels stay ephemeral until Ergo enables channel registration. **ionos**
must turn on NickServ + ChanServ, then recycle `bob-ionos` so it
`REGISTER`s `#ionos` after JOIN.

**Operator runbook (action this):** `docs/ergo-chanserv-enable-bob-shops.md`

Minimum Ergo knobs (then `Restart-Service BobIrcd`):

```yaml
accounts:
  authentication-enabled: true
  registration:
    enabled: true
channels:
  registration:
    enabled: true
```

Verify: `/msg ChanServ INFO #ionos` — expect registered with founder `bob-ionos`
after the ear logs `INFO chanserv REGISTER #ionos`.

## Jeeves (digest chair)

Nick `Jeeves`, `irc_agent.py --chair`.

| | Path |
|---|---|
| `--home` / `AGENTIC_IRC_HOME` | `~\.agentic-irc-jeeves` |
| `BOB_DIGEST_HOME` (`digest.json`, `chair-outbox.txt`) | `~\.agentic-irc-bobiverse` |

`scripts/Install-BobChair.ps1` sets both and stops a prior `--chair` / nick
`Jeeves` before start. Do not share `--home` with `bob-ionos`.

BobIrcd NSSM and the hook that starts Jeeves when the IRC server starts live
in **agentic_build** (`chairNick` `Jeeves`). This repo does not define that
service.
