<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-mode3-win95-thin-moot-cli-2026-09-19.md, last changed 2026-09-19. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request — Mode 3: Win95-era thin moot CLI (2026-09-19)

**Status:** first ticket on `main` (P0–P3). Not ready for human UAT. Win95 TLS **not** claimed (`docs/mode3-tls-spike.md`).  
**Repo:** SimonBarnett/agentic_irc  
**Related:** Mode 1 (agent↔agent SEAL), Mode 2 (moot + FILE), Mode DUMB (Server 2012 `dumb_agent.py` / deferred .NET Phase 5). Mode 3 is **not** a reimplementation of Phase 5; it is a new product surface.

## One-line goal

Ship a **single native Windows console EXE** that a human runs on ancient-through-modern Windows. It **joins a moot** as a thin command-line client so moot agents can **send shell commands** and **receive stdout/stderr**, then publish that EXE as a **GitHub Release** that **rebuilds update**.

## Why (operator story)

1. Operator copies `airc-moot-thin.exe` (and a tiny config / key drop) onto a box that may be as old as **Windows 95** (exclude Windows ME).
2. Operator runs it; it connects to Libera TLS, joins the private channel, and **JOINs the named moot** as a non-LLM participant.
3. A chair/agent with floor (or an operator allowlist — see LOCKED vs UNKNOWN) sends a command.
4. The thin client runs the command under a **jail + allowlisted bins**, returns **stdout/stderr/rc** into the moot (or DUMB-shaped sealed result — see protocol).
5. Rebuilds of the same artefact land on the **same GitHub Release** (tag `mode3-thin` or `airc-moot-thin-v*`) so operators always download the latest known-good binary.

## LOCKED

| ID | Rule |
|---|---|
| L1 | **Backwards compatibility bar:** one Win32 **ANSI** PE (console subsystem) that is intended to run on **Windows 95 OSR2, 98, NT 4, 2000, XP, Vista, 7, 8, 10, 11, Server 2003–2022**. Explicitly **exclude Windows ME**. Document any API that forces a higher floor. |
| L2 | **Not an LLM.** No model, no Grok, no Python runtime required on the target box. |
| L3 | **Moot membership.** Client must OPEN/JOIN (or JOIN only if chair already opened) a moot id supplied by config/CLI; appear on roster; participate as thin CLI (SAY of results and/or sealed job replies). |
| L4 | **Command relay.** Agents (or allowlisted operators) can pass a command; thin client executes and returns **stdout, stderr, exit code**. Truncation must be honest (`truncated: true` + spill file under jail if over cap). |
| L5 | **Jail + allowlist.** Same spirit as DUMB: `--allow-path` jail, default bins (`cmd.exe`, `hostname.exe`, `ipconfig.exe`, `whoami.exe`; PowerShell only when OS supports it). Unknown operator / empty allowlist → **no exec**, no result ciphertext on the wire. |
| L6 | **Secrets off-channel.** PSK / connector key generated off IRC; never printed; fingerprint compare OOB. No `password=` or API key assignments in repo or release notes. |
| L7 | **GitHub Release.** Binary (and checksums) published under `SimonBarnett/agentic_irc` Releases. **CI rebuild updates that release** (replace assets on a stable tag, or move `mode3-thin-latest` + keep versioned tags — pick one in Phase 0 and stick to it). |
| L8 | **Offline tests first.** CI must not open Libera. Protocol/unit tests on a modern builder; ancient OS smoke is manual or VM matrix documented in `/docs`. |
| L9 | **Do not break** existing Mode 1/2 Python `irc_agent` / moot / FILE / DUMB Python paths unless marked compatible extension. |
| L10 | Artefact name: **`airc-moot-thin.exe`** (plus `.sha256`). Optional companion `.ini` / `.cfg` example in release zip. |

## UNKNOWN (Phase 0 must close before claiming Win95 works)

| ID | Question | Exit criteria |
|---|---|---|
| U1 | Can Libera **TLS 1.2+** be spoken from Win95 without a modern Schannel? | Spike: static mbedTLS/LibreSSL vs external relay. Document floor OS if Win95 cannot do TLS. |
| U2 | Is "DOS program" literal **16-bit real-mode DOS**, or **Win32 console that feels like DOS**? | Default assumption until closed: **Win32 ANSI PE** (L1). If Simon insists on true DOS, need a DOS TCP+TLS stack plan or a userspace relay on a newer hop. |
| U3 | Wire shape: reuse **DUMB v1** sealed jobs inside moot, or new **MOOT-CLI v1** verbs? | Prefer reuse DUMB job JSON (`exec`/`ping`/`sysinfo`) + moot presence, unless moot floor semantics demand new verbs. |
| U4 | Who may exec: moot floor holder only, chair only, or `--operators` nick list (DUMB-style)? | Security default: **operators allowlist**; floor alone is not enough. Confirm with Simon if softer. |
| U5 | Toolchain on CI: OpenWatcom / MinGW-w64 with `-municode` off / MSVC with `WINVER=0x0400`? | One primary toolchain documented; second is optional. |
| U6 | Release strategy: mutable tag `mode3-thin` vs immutable `airc-moot-thin-vX.Y.Z` + `latest`? | Document in `docs/mode3-release.md`. |

## Non-goals (this FR)

- Completing deferred **.NET 4.5 Phase 5** `airc-dumb.exe` stub (separate ticket).
- GUI, service wrapper, or auto-update beyond "download new release".
- Running on Windows ME.
- Opening Libera from GitHub Actions.
- Shipping Python/Node on the ancient host.

## Acceptance (first shippable)

| ID | Criterion |
|---|---|
| A1 | `airc-moot-thin.exe` builds on CI (or documented one-box build) and attaches to a GitHub Release on `agentic_irc`. |
| A2 | Rebuild of main (or release workflow) **updates** that release's assets + checksums. |
| A3 | Offline tests cover: jail refuse, unknown operator drop, exec stdout/rc framing, truncation flag, config parse. |
| A4 | Manual doc: how to run on XP+ today; honest matrix row for Win95/98/NT4 (pass / fail / blocked on U1). |
| A5 | Live smoke on IONOS (modern Windows): join moot with `cm-bob` chair + thin client nick; exec `hostname`; stdout visible to chair. |
| A6 | Bob hostile MRB may pass **ready for human UAT** only when A1–A5 hold and U1–U4 are closed or explicitly waived in `/docs`. |

## Suggested tree

```
src/moot_thin/          # C (or C++) Win32 ANSI sources
  main.c
  irc_tls.c             # TLS + IRC (or stub + spike notes)
  moot.c
  dumb_job.c            # reuse DUMB job shapes if U3 says so
  jail.c
  README.md             # WINVER, toolchain, known OS floors
.github/workflows/mode3-thin-release.yml
docs/feature-request-mode3-win95-thin-moot-cli-2026-09-19.md  # this file
docs/feature-request-mode3-win95-thin-moot-cli-2026-09-19.pdf
docs/build-and-test-plan-mode3.md
docs/mode3-release.md   # after U6
tests/test_moot_thin_*.py   # protocol fixtures / golden vectors (offline)
```

## Kickoff for build agent

1. Park/confirm this FR + write `docs/build-and-test-plan-mode3.md` executable without more questions.
2. Close U2/U3/U4 in the plan with **stated defaults** (Win32 ANSI; DUMB jobs + moot JOIN; `--operators`).
3. Spike U1 on paper + smallest linkable TLS; if Win95 TLS impossible, document **minimum OS** and still ship XP+/modern binary + release pipeline (do not silently claim Win95).
4. Implement minimal viable thin client against existing Python moot/DUMB for IONOS smoke.
5. Wire GitHub Release workflow (A1–A2).
6. Offline tests (A3). Push. Stop for Bob MRB — do **not** claim human UAT.

## Relationship to existing dumb connector

| | DUMB (Mode "ancient host") | Mode 3 thin moot CLI |
|---|---|---|
| Primary host floor | Server 2012 + Python ref / .NET 4.5 stub | Win95→modern Win32 ANSI (excl. ME) |
| Presence | CAPA on channel | **Moot roster** + jobs |
| Exec model | Sealed DUMB jobs from `--operators` | Same spirit; moot-visible |
| Ship form | `airc-dumb` stub today | **`airc-moot-thin.exe` Release** |

Do not delete or regress `scripts/dumb_agent.py` while building Mode 3.