<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/mrb-wp-p5-dotnet-2026-09-19.md, last changed 2026-09-25. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Hostile MRB - WP-P5 net45 airc-dumb.exe (2026-09-19)

**Repo:** SimonBarnett/agentic_irc
**Commit:** 2751f54 feat: WP-P5 net45 airc-dumb.exe protocol clone
**Job:** ionos 1299cb65
**Spec:** docs/gap-vs-feature-request-2026-09-19.md remaining item 1; docs/wp-backlog-full-irc-2026-09-19.md WP-P5

## Verdict

**PASS-with-nits** for the Phase 5 protocol clone (offline).
**Not ready for human UAT** of Server 2012 live Libera until a manual/field smoke is logged.

## Evidence

| Check | Result |
|---|---|
| Tree | Connector.cs, JobRunner.cs, DumbCrypto.cs, Aes256Gcm.cs, Program.cs; csproj TargetFrameworkVersion v4.5 |
| `--selftest` | ok: empty operators, jail, AES-GCM vector+roundtrip, n=100 drop, operator drop, ping, exec, truncation, D2 no ciphertext, CAPA |
| `pytest -q` with DOTNET_DUMB_EXE | **114 passed, 1 skipped** (Unix chmod) |
| Python dumb / Mode 3 | Untouched except honesty notes |
| Libera from CI | Still forbidden |
| Docs honesty | README + skill + gap: clone present, pending Bob MRB / not self-UAT |

## Closed vs prior stub

| Expectation | Disposition |
|---|---|
| No longer INFO+exit 0 stub | **Closed** |
| TcpClient + SslStream TLS 1.2 | **Present** (selftest CAPA path) |
| CAPA / PSK DUMB jobs | **Present** |
| Jail + unknown operator no result | **Present** (D2 selftest) |
| Truncated spill | **Present** |
| No runtime NuGet crypto | **Present** (in-tree AES-GCM) |

## Nits / follow-ups

1. **Live Server 2012 + Libera smoke** still human/manual (gap + skill). Log under /docs when run; required before Bob says ready for human UAT of the 2012 adapter.
2. Confirm `airc-dumb.exe` stays gitignored (local build artefact on ionos clone OK).
3. Refresh WP backlog: mark WP-P5 engineering closed pending live smoke.

## Non-claims

- Not Mode 3 UAT (separate A5 job).
- Not AGPK-mode dumb jobs (WP-AGPK still open).
- Not Win95.

## Hand-off

No immediate rebuild required for offline clone. Optional later: live 2012 smoke ticket.
