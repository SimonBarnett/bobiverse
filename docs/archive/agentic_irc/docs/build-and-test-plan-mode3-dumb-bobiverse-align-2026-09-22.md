<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-mode3-dumb-bobiverse-align-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build-and-test plan: Mode 3 DUMB vs new bobiverse setup

**FR:** `docs/feature-request-mode3-dumb-bobiverse-align-2026-09-22.md`
**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/86
**Repo:** SimonBarnett/agentic_irc
**Kickoff:** read the FR + this plan. Implement M3B1–M3B7. Commit and push a PR. Do not stamp UAT. Do not merge main as implementer unless harvest skill says so — open a PR.

## Goals

Align Mode 3 thin + DUMB **docs, skills, and defaults** with the live Ergo fleet without turning the elder exe into a `bob-*` talk seat.

## Non-goals

- Win95 TLS. Digest row for field boxes. Tray #142. Changing DUMB PSK crypto. Live IRC from CI. UAT stamp.

## Phase order

### P0 — Docs + skills (exit: M3B1, M3B2, M3B6)

1. `src/moot_thin/README.md`, `docs/mode3-zero-config-2026-09-19.md`, `docs/mode3-tls-spike.md` (add an Ergo-first sentence; keep the Libera TLS science as **legacy**), `docs/mode3-os-matrix.md` (column “TLS to Ergo” or footnote that the live floor is Ergo, same Schannel 1.2).
2. `.grok/skills/invite-airc/SKILL.md`: hard rule do not `--channel "#bobiverse"`; `--host irc.ntsa.uk` required on chair; Mode 3 `--chair` ≠ Jeeves.
3. `.grok/skills/agentic-dumb/SKILL.md` + `.grok/skills/agentic-irc/SKILL.md`: two-chair sentence; Mode 3 not a git worker / not digest writer / not `{machine}-{pid}`.
4. `airc-moot-thin.ini.example`: comment that `#bobiverse` is forbidden as pairing; host already Ergo.

### P1 — Defaults (exit: M3B3, M3B4, M3B5)

1. Stop filling `{nick}-online` in `config_defaults` / self-heal unless `--hello` or ini `hello=` set. `say()` hello only when non-empty.
2. Self-heal nick = `m3-` + sanitized hostname (truncate to 32). CLI/ini still win. Already-paired `paired.ini` nick stays (do not rename a live pair).
3. Chair copy-paste in `pair.c` includes `--host irc.ntsa.uk` (and `--port` if not 6697).
4. Optional: `invite-airc` / chair warn if channel is `#bobiverse` (log + refuse GRANT happy-path). Prefer refuse.

### P2 — Tests (exit: M3B7)

1. Pytest: Mode 3 happy-path docs must contain `irc.ntsa.uk` and must not tell operators to join Libera as the default.
2. Pytest or `--selftest`: default hello empty; nick prefix `m3-` on zero-arg self-heal fixture (update `walrus` / `walrus-online` assertions in `main.c` selftest — that fixture used hostname `walrus`; new default nick `m3-walrus`, hello empty).
3. Pytest: chair fallback line has `--host`.
4. Existing `tests/test_moot_thin_proto.py` / `test_dumb_dotnet.py` stay green.
5. `src/moot_thin/build.bat` + `airc-moot-thin.exe --selftest` on the Windows builder.

### P3 — PR

1. Branch `work/fr-mode3-bobiverse-align`.
2. Open PR linking the issue. Do not merge. Do not stamp UAT.
3. Paste test summary on the PR.

## Suggested tree

- `src/moot_thin/config.c`, `main.c` (selftest nick/hello), `pair.c`, `pair.h` (default channel may stay `#airc-moot`)
- `src/moot_thin/README.md`, `airc-moot-thin.ini.example`
- `.grok/skills/{invite-airc,agentic-dumb,agentic-irc}/SKILL.md`
- `docs/mode3-*.md` (Ergo-first, Libera legacy)
- `tests/test_moot_thin_proto.py` (or new `tests/test_mode3_bobiverse_align.py`)

## Locked constants

- Host `irc.ntsa.uk` port `6697`
- Pairing default channel `#airc-moot` (private). **Not** `#bobiverse`
- Fleet moot `b0b1be15e0000001` is **not** the Mode 3 pairing moot
- Digest chair nick `Jeeves`
- Report URL is unrelated (do not call it from Mode 3)
- Fixture PIN `482917` stays a test vector only

## Test IDs

| ID | Command / check |
|---|---|
| T1 | `pytest -q` |
| T2 | `airc-moot-thin.exe --selftest` |
| T3 | grep skills/README: Ergo first; `#bobiverse` pairing forbidden; two chairs |
| T4 | self-heal nick `m3-…`; hello empty unless set |

CI: no Ergo, no Libera.

## Definition of done (first ticket)

P0+P1+P2 on a PR. T1+T2 green. Issue comment with SHA. Stop. Bob MRBs.

## Kickoff prompt (`Start-BobBuild -Goal`)

Read `docs/feature-request-mode3-dumb-bobiverse-align-2026-09-22.md` and `docs/build-and-test-plan-mode3-dumb-bobiverse-align-2026-09-22.md`. Implement P0–P2. Open a PR. Do not merge main. Do not stamp UAT. Do not put password= or API key assignments in prompts or commits. Do not JOIN or test against live IRC from CI. Mode 3 is not a git worker — you are editing the agentic_irc tree on a normal build box.
