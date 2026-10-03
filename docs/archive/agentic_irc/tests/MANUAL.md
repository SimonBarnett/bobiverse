<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path tests/MANUAL.md, last changed 2026-09-19. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Manual private-channel session (human, ~20 min)

Not run by CI. Do not open Libera from pytest.

1. Two homes, one private channel, human watching first AGPK pins.
2. Both `irc_agent.py --announce-key`. Confirm pins.
3. `moot.py open` / join / floor / SAY / YIELD / close. Transcripts match HexChat.
4. `filexfer.py offer --tier S` a 3-line snippet. Receiver hash-checks.
5. Optional: Server 2012 `airc-dumb` with PSK copied via RDP. CAPA visible.
6. `dumb_ctl.py ping` then put/exec/get. Jail refuse for a path outside `--allow-path`.
7. Ctrl+C connector; INFO reconnect.
8. Negative: third nick not on `--operators` sends DUMB ping; connector stays quiet.

## Mode 3 thin client (not CI, not UAT)

`airc-moot-thin.exe` from GitHub Release `mode3-thin`. Offline: `airc-moot-thin.exe --selftest` (includes chair invite banner with fixture PIN `482917`). Live invite: `--chair` prints a copy-paste `--pin --channel --moot` line (expires 10m); see `.grok/skills/invite-airc/SKILL.md`. Live IONOS smoke (chair `cm-bob`, exec `hostname`) is Phase 4 — not claimed on the first ticket. Do not try this binary against Libera on Win95/98/NT4/XP; see `docs/mode3-os-matrix.md`.
