<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/mode3-tls-spike.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Mode 3 TLS spike (U1) — 2026-09-19

**Live floor (2026):** Mode 3 production IRC is private Ergo **`irc.ntsa.uk:6697`** (Let's Encrypt, Schannel TLS 1.2). **Libera is legacy only** for this kit; the TLS science below still describes that public service.

**Question:** Can legacy public IRC **TLS 1.2+** (with SNI) be spoken from Windows 95 without a modern Schannel?

**This ticket's decision:** **No claim that Win95 (or 98 / NT4 / XP) can complete a live TLS IRC handshake.** Ship a **32-bit Win32 ANSI console PE** that uses **Schannel** on modern Windows. Document the floor honestly. Do not silently advertise Win95.

## What Libera needs

- TLS **1.2 or newer**. TLS 1.0/1.1 are not accepted.
- **SNI** on the ClientHello (`irc.libera.chat`).
- A **current CA** (Let's Encrypt / ISRG). Handshake fails if the box has only 1990s roots.
- Modern cipher suites (ECDHE + AES-GCM is typical). RC4 / SSLv3 will not work.

These are protocol facts about the public service as of 2026, not a guess about this repo.

## What each OS can actually do

| Stack | TLS 1.2 | SNI | Modern CA store | Notes |
|---|---|---|---|---|
| Win95 Schannel (OSR2, IE optional) | **No** | **No** | **No** | SSL 2/3, maybe TLS 1.0 with later IE. No `SP_PROT_TLS1_2_CLIENT`. |
| Win98 / ME Schannel | **No** | **No** | **No** | ME is **excluded** by the FR. |
| NT4 Schannel | **No** | **No** | **No** | Same TLS 1.0-era ceiling. |
| XP SP3 Schannel | **No** (official) | Limited / no | Stale | Official Schannel tops out at TLS 1.0. Unofficial "POSReady" TLS 1.2 hacks exist; **not** a supported path. |
| Vista / Win7 Schannel | Yes **with updates** | Yes on 7 with hotfix | Must be updated | Win7 needs KB3140244 (and friends) plus a current root pack. |
| Win8 / Server 2012+ Schannel | **Yes** | **Yes** | Yes if updated | This is the intended live path. |
| Static mbedTLS / LibreSSL linked into a Win95 PE | Theoretically TLS 1.2+SNI | In-library | **Must bundle a CA file** | Needs Winsock 2 on OSR2, an ancient CRT (OpenWatcom / very old MinGW), and a shipped root bundle. Not done this ticket. Untested. Do not claim. |
| Userspace relay (newer hop terminates TLS, forwards clear IRC to Win95) | N/A | N/A | N/A | Out of scope. Cleartext hop is hostile on a shared LAN. |

## Toolchain vs load vs live

Two different floors:

1. **PE load floor.** This artefact is compiled with `_WIN32_WINNT=0x0501` (XP) as a 32-bit ANSI console. It imports Winsock2, Schannel (`secur32`), CryptoAPI. It will **not** load on Win95/98/NT4. That is intentional for this ticket, not an accident to paper over.
2. **Live Ergo / legacy Libera floor.** Schannel TLS 1.2 + SNI + current CA to `irc.ntsa.uk` (or legacy `irc.libera.chat`). **Windows 8 / Server 2012 or newer** is the expected-good row. Windows 7 SP1 with TLS 1.2 enabled is "possible, untested here." XP and older are **blocked on U1**.

## What we did **not** run

- No Win95 VM link of mbedTLS.
- No OpenWatcom Win95 PE.
- No packet capture of a 9x box against `irc.libera.chat`.
- No claim that a static TLS library "would just work" once someone copies the exe.

A later ticket may try OpenWatcom + mbedTLS 2.x + bundled ISRG Root X1 and record a pass/fail row. Until that evidence exists in `/docs`, **Win95 stays blocked**.

## Choice for this artefact

| Item | Choice |
|---|---|
| TLS library | Windows **Schannel** (`InitializeSecurityContext` / `EncryptMessage`) |
| Protocols enabled | `SP_PROT_TLS1_2_CLIENT` (and TLS 1.3 if the OS offers it via the same path) |
| Certificate check | Left **on** (`SCH_CRED_AUTO_CRED_VALIDATION`). Do not ship a "skip verify" flag. |
| DUMB crypto | Software **AES-256-GCM** (same shape as Python `seal.dumb_seal_bytes`). Not CNG, so job sealing does not depend on Vista+ BCrypt. |
| Ancient-OS story | Documented blocked. Operators on XP-era boxes use a **newer hop** or wait for a future static-TLS spike. |

## Exit for U1

**Closed for this ticket as: Win95 cannot be claimed.** Minimum OS for a live Ergo join with *this* binary: **Windows 8 / Server 2012+** (Win7 SP1 + TLS 1.2 = untested possible). XP-or-newer is the compile/load story only.
