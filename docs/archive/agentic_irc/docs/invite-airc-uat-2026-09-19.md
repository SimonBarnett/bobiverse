<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/invite-airc-uat-2026-09-19.md, last changed 2026-09-19. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Invite-airc live UAT (IONOS) — 2026-09-19

**Tip:** `978e12a` feat: --chair prints copy-paste thin invite (v0.2.1)  
**Machine:** IONOS, Windows Server 2022 Datacenter (`WIN-MPRE8VI4U6U`)  
**Channel:** `#cm-bob-oscar`  
**Chair nick:** `cm-inv` (`airc-moot-thin.exe --chair --once`)  
**Thin nick:** `cm-invt` (copy-paste invite line + same-box `--nick` / `--home`)  
**Moot:** `d3a6414017ede995`  
**Job id:** `5f3f90d778ec59c5` (`exec hostname`)

This is live evidence for `docs/feature-request-invite-airc-2026-09-19.md` I2/I3/I4 and plan P3. **Does not** claim Windows 95 TLS. Live PIN and connector keys are **not** in this file or in git.

## Binary

Local i686 gcc rebuild of `src/moot_thin` at `978e12a` (exe is gitignored).

- Version: `0.2.1` / `ptr=4` (32-bit)
- SHA-256: `3e60c0f4e1b3f65b2fd1f2f0e687911e0f568cae4a37877946e0c5e53c8f8ab8`
- `--selftest`: `INFO selftest ok` including `chair invite banner ok` (fixture PIN `482917` only)

## Libera cap

Unregistered cap is 3 from this IP. `cm-oscar` was paused for the pair + exec, then restored. `cm-bob` stayed up. No leftover `cm-inv` / `cm-invt` after the run.

## Commands (PIN redacted)

Same-box isolation used extra `--nick` / `--home` / `--once`. Field ritual remains: copy the `airc` folder, run the one line `--chair` printed.

```
airc-moot-thin.exe --chair --channel "#cm-bob-oscar" --nick cm-inv --home C:\Users\Administrator\.airc-invite-chair --once

# stdout (redacted):
INFO PIN REDACTED   moot=d3a6414017ede995   channel=#cm-bob-oscar   expires 10m
INFO copy-paste thin (expires 10m):
airc-moot-thin.exe --pin REDACTED --channel "#cm-bob-oscar" --moot d3a6414017ede995

airc-moot-thin.exe --pin REDACTED --channel "#cm-bob-oscar" --moot d3a6414017ede995 --nick cm-invt --home C:\Users\Administrator\.airc-invite-thin --once
```

Hostname smoke used a short-lived Python `irc_agent.py` as `cm-inv` after chair `--once` exited (C chair has no send-job CLI). PSK was the GRANT-delivered 32-byte key; not pasted.

## Evidence

### Chair stdout (redacted)

```
INFO key saved
INFO keyfp=de18abaa92a101d00018f48890addfe481d0044176e0e0a9cfa6adcf437a8435
INFO PIN REDACTED   moot=d3a6414017ede995   channel=#cm-bob-oscar   expires 10m
INFO copy-paste thin (expires 10m):
airc-moot-thin.exe --pin REDACTED --channel "#cm-bob-oscar" --moot d3a6414017ede995
INFO airc-moot-thin 0.2.1 nick=cm-inv jail=C:\Users\Administrator\.airc-invite-chair\jail ptr=4
INFO connecting irc.libera.chat:6697 tls=1
INFO lobby chair waiting for HELLO
INFO pin=ok granted to cm-invt
```

Invite line contains `--pin`, `--channel`, `--moot`. Expires note is `expires 10m`. No long-term PSK on stdout or on IRC.

### Thin stdout (redacted)

```
INFO airc-moot-thin 0.2.1 nick=cm-invt jail=C:\Users\Administrator\.airc-invite-thin\jail ptr=4
INFO connecting irc.libera.chat:6697 tls=1
INFO lobby waiting for PIN pair
INFO pair hello sent
INFO key saved
INFO joined as cm-invt moot=d3a6414017ede995 pin=ok
INFO pin=ok operators=cm-inv
INFO dumb job id=5f3f90d778ec59c5 from=cm-inv
```

### Hostname on the chair

DUMB result `to=cm-inv from=cm-invt` decrypted with the GRANT PSK (not committed):

```json
{
  "v": 1,
  "op": "exec",
  "id": "5f3f90d778ec59c5",
  "ok": true,
  "rc": 0,
  "stdout": "WIN-MPRE8VI4U6U\r\n",
  "stderr": "",
  "truncated": false
}
```

`hostname.exe` on this box prints the same name. Ciphertext was not pasted.

## Offline

`pytest -q` with `AIRC_MOOT_THIN_EXE` set: **123 passed, 1 skipped**. `--selftest` prints the fixture banner:

```
airc-moot-thin.exe --pin 482917 --channel "#ops" --moot 0123456789abcdef
```

`482917` is the documented fixture, not a live PIN.

## Non-claims

- Windows 95 / 98 / NT4 / XP live Libera: still blocked (U1).
- Walrus USB-copy field box: not run this ticket (second nick on IONOS used instead, per plan).
- Ready for human UAT: Bob's phrase. Evidence is parked for that review.
