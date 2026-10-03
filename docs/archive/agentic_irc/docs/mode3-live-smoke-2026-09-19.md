<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/mode3-live-smoke-2026-09-19.md, last changed 2026-09-19. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Mode 3 live IONOS smoke (A5) — 2026-09-19

**WP:** WP-M3-A5  
**Machine:** IONOS, Windows Server 2022 Datacenter (`WIN-MPRE8VI4U6U`)  
**Channel:** `#cm-bob-oscar`  
**Chair:** `cm-bob` (existing Mode 2 Python `irc_agent.py`)  
**Thin nick:** `cm-thin`  
**Moot:** `4a9a915e3a97b319`  
**Job id:** `d4ff0b48526526ed` (`exec hostname`)

This is live evidence for A5. **Not** ready for human UAT (Bob MRB). **Does not** claim Windows 95 TLS. Phase 5 .NET was not touched.

## Binary

Release tag `mode3-thin` (`airc-moot-thin` 0.1.0, SHA-256 `506598dda12122491a09bc55a4cd10959522c60e701201cb0cf9539c67654835`) failed the Schannel handshake (`SEC_I_INCOMPLETE_CREDENTIALS` / `90320`). Local gcc i686 rebuild of `src/moot_thin` after the handshake + `CAP END` fixes was used for the successful session.

- Artefact: `src/moot_thin/airc-moot-thin.exe` (not git-tracked)
- Version: `0.1.0` / `ptr=4` (32-bit)
- SHA-256: `F9491C7A24D184C7DB4AFFB48C97EB788B84601E4C0CD09A18E9BD8B0E86A98E`
- Selftest: `INFO selftest ok`

## Bugs found (fixed in this ticket)

1. **Schannel handshake.** Incomplete ServerHello tokens were discarded (`SEC_E_INCOMPLETE_MESSAGE` → `SEC_E_INVALID_TOKEN` / `80090308` on the gcc build). Libera may send `CertificateRequest`; `SCH_CRED_NO_DEFAULT_CREDS` then returned `SEC_I_INCOMPLETE_CREDENTIALS` on the MSVC release. `irc_tls.c` now keeps incomplete input, sets `ISC_REQ_USE_SUPPLIED_CREDS`, and retries an empty client cert.
2. **IRCv3 registration.** Client sent `CAP LS 302` and never `CAP END`, so Libera withheld numeric `001`. `main.c` now sends `CAP END` after `NICK`/`USER` (no SASL).

Connector PSK was generated **off channel** (`python scripts/seal.py dumb-key`). Fingerprint (SHA-256 of the 32 raw bytes): `f1af806b931c8d7a8f5298b2577d677f1dae1efcf11fcf070d632ad683aef304`. Key file was not committed.

Libera allows three unregistered connections from this IP. `cm-spider` was paused for the thin JOIN, then restarted. `cm-bob` and `cm-oscar` stayed up.

## Commands (secrets redacted)

Homes were `C:\Users\Administrator\.agentic-irc-bob` (chair) and `C:\Users\Administrator\.agentic-irc-thin` (thin). `#` in the channel must be quoted in PowerShell.

```
python scripts\seal.py dumb-key --home C:\Users\Administrator\.agentic-irc-thin
# copy connector.key to chair home\dumb\  (same user; AIRC1+DPAPI)

python scripts\moot.py --home C:\Users\Administrator\.agentic-irc-bob open --id 4a9a915e3a97b319 --nick cm-bob --channel "#cm-bob-oscar" --topic "mode3 A5 IONOS live smoke" --mode floor

airc-moot-thin.exe --nick cm-thin --channel "#cm-bob-oscar" --moot 4a9a915e3a97b319 --home C:\Users\Administrator\.agentic-irc-thin --allow-path C:\Users\Administrator\.agentic-irc-thin\jail --operators cm-bob --key C:\Users\Administrator\.agentic-irc-thin\dumb\connector.key --hello thin-online --once

python scripts\dumb_ctl.py --home C:\Users\Administrator\.agentic-irc-bob --channel "#cm-bob-oscar" --from-nick cm-bob --to cm-thin exec --argv hostname

python scripts\moot.py --home C:\Users\Administrator\.agentic-irc-bob close --id 4a9a915e3a97b319 --nick cm-bob --channel "#cm-bob-oscar" --summary "mode3 A5 live smoke done"
```

`--operators cm-bob` was required. Floor was not granted; exec still ran.

## Evidence

### Thin stdout

```
INFO keyfp=f1af806b931c8d7a8f5298b2577d677f1dae1efcf11fcf070d632ad683aef304
INFO airc-moot-thin 0.1.0 nick=cm-thin jail=C:\Users\Administrator\.agentic-irc-thin\jail ptr=4
INFO connecting irc.libera.chat:6697 tls=1
INFO joined #cm-bob-oscar as cm-thin moot=4a9a915e3a97b319
INFO dumb job id=d4ff0b48526526ed from=cm-bob
```

### Chair stdout (`cm-bob` `agent.out`)

```
INFO no-sasl
INFO joined #cm-bob-oscar as cm-bob
INFO capa from=cm-thin
INFO dumb job id=d4ff0b48526526ed from=cm-thin
```

### Chair roster (disk; IRC does not echo own OPEN)

After JOIN:

```json
{
  "id": "4a9a915e3a97b319",
  "state": "open",
  "chair": "cm-bob",
  "roster": ["cm-bob", "cm-thin"],
  "topic": "mode3 A5 IONOS live smoke"
}
```

After CLOSE: `state=closed`, roster still `cm-bob, cm-thin`.

Transcript (`moot/4a9a915e3a97b319.txt`):

```
… cm-bob OPEN mode3 A5 IONOS live smoke
… cm-thin JOIN
… cm-bob CLOSE mode3 A5 live smoke done
```

### Hostname stdout on the chair

DUMB result `to=cm-bob from=cm-thin` decrypted with the off-channel PSK (chair `irc.log` + `dumb/connector.key`) into `dumb/results/d4ff0b48526526ed.json`:

```json
{
  "v": 1,
  "op": "exec",
  "id": "d4ff0b48526526ed",
  "ok": true,
  "rc": 0,
  "stdout": "WIN-MPRE8VI4U6U\r\n",
  "stderr": "",
  "truncated": false
}
```

`hostname.exe` on the box prints the same name. Ciphertext was not pasted here.

## Non-claims

- Windows 95 / 98 / NT4 / XP live Libera: still blocked (U1). This run is Win8+ / Server 2022 Schannel TLS 1.2+.
- Ready for human UAT: **not claimed**. Bob MRB after this log.
- Phase 5 `.NET` `airc-dumb`: not in this job.
- GitHub Release `mode3-thin` assets will pick up the handshake/`CAP END` fix on the next green `src/moot_thin/**` build.
