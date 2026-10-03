<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-mode3.md, last changed 2026-09-19. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan — Mode 3 Win95-era thin moot CLI

**Spec:** [feature-request-mode3-win95-thin-moot-cli-2026-09-19.md](./feature-request-mode3-win95-thin-moot-cli-2026-09-19.md) (+ PDF sibling)  
**Model preference:** build0.1 when CLI supports it  
**Machine preference:** ionos

## Defaults for UNKNOWNs (until Simon overrides)

| ID | Default |
|---|---|
| U2 | Win32 ANSI console PE (not 16-bit DOS) |
| U3 | Reuse DUMB v1 sealed job JSON (`ping`/`sysinfo`/`exec`) + moot JOIN/roster |
| U4 | `--operators` nick allowlist required for exec (floor alone insufficient) |
| U6 | Immutable tags `airc-moot-thin-vX.Y.Z` + rolling release/tag `mode3-thin` whose assets are replaced on each green main build of `src/moot_thin/**` |
| U1 | Spike first; if Win95 cannot TLS 1.2 to Libera, document minimum OS in README and still ship XP+ binary + release pipeline — **do not claim Win95 pass** |

## Phase order

### P0 — Spike + docs (exit: U1 paper decision + tree scaffold)
- Create `src/moot_thin/README.md` with WINVER/toolchain notes.
- Spike notes for TLS on Win95 (static mbedTLS vs Schannel floors).
- Write `docs/mode3-release.md` draft (U6 default).
- Exit: committed spike notes; no false Win95 claim.

### P1 — Protocol fixtures (offline)
- Golden vectors for DUMB exec request/response framing used by thin client.
- Jail/operator-drop cases as Python tests or C unit tests runnable on CI builder.
- Exit: `pytest -q` (or documented C test runner) green; no Libera.

### P2 — Minimal Win32 thin client (modern builder OK)
- CLI: nick, channel, moot id, home, allow-path, operators, key path.
- Connect TLS (Schannel on modern; spike path documented for ancient).
- JOIN moot; announce presence; accept sealed exec from operators; return stdout/stderr/rc.
- Exit: binary builds; offline tests; IONOS live smoke optional this phase.

### P3 — GitHub Release pipeline
- Workflow builds `airc-moot-thin.exe` + `.sha256`.
- Publishes/updates `mode3-thin` release assets; also version tag when VERSION bumps.
- Exit: A1–A2 demonstrable on a dry-run or real release (prefer real on `SimonBarnett/agentic_irc`).

### P4 — Manual matrix + smoke
- Doc table: Win95 / 98 / NT4 / XP / modern — pass/fail/blocked.
- IONOS smoke with chair `cm-bob` + thin nick: exec hostname → stdout to chair.
- Exit: A4–A5 evidence in `/docs` (log excerpt OK).

## Definition of done (first ticket)

- FR + this plan + PDF in `/docs` (Bob parks PDF if agent cannot).
- P0–P1 complete; P2 skeleton compiling OR honest blocker in gap doc.
- Release workflow at least drafted in-repo.
- **Not** ready for human UAT until Bob MRB says so after A1–A5.

## Kickoff prompt block (Start-BobBuild -Goal)

Read `docs/feature-request-mode3-win95-thin-moot-cli-2026-09-19.md` and `docs/build-and-test-plan-mode3.md`. Implement P0 then P1 then as much of P2–P3 as fits. Prefer Win32 ANSI + DUMB jobs + moot JOIN + operators allowlist. Do not claim Win95 TLS works without spike evidence. Do not break Mode 1/2 Python. Commit and push. Paste test summary. Do not claim ready for human UAT.

## Constraints

- No real secret assignments in prompts or commits.
- No Libera from CI.
- Do not finish deferred .NET Phase 5 in this ticket unless trivial leftover.
- Prefer cheapest capable model (build0.1) when available.