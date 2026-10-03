<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-invite-airc-2026-09-19.md, last changed 2026-09-25. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request - invite-airc skill + chair invite one-liner (2026-09-19)

**Status:** parked for build agent
**Repo:** SimonBarnett/agentic_irc
**Related:** Mode 3 zero-config v0.2.0 (2b1d743), docs/mode3-zero-config-2026-09-19.md, skill invite-airc

## Charge

Standing operator ritual for elder machines:

1. Ask the agent for a **command** (includes PIN).
2. Copy `airc` to the machine.
3. Run the command.

Ship first-class support so Bob/agents do not improvise.

## LOCKED

| ID | Rule |
|---|---|
| I1 | Skill `invite-airc` lives in `.grok/skills/invite-airc/SKILL.md` (leaflet already parked; keep in sync with behaviour). |
| I2 | `airc-moot-thin.exe --chair` stdout MUST include a ready-to-copy **thin invite line** containing `--pin`, `--channel`, and `--moot` (and note TTL). |
| I3 | Thin happy path is that one line after copying the folder; self-heal nick/home/jail. |
| I4 | No long-term PSK on IRC; PIN wrap/GRANT unchanged. |
| I5 | README + agentic-irc / agentic-moot cross-links to invite-airc. |
| I6 | Offline selftest covers that --chair banner contains `--pin` and `--moot` tokens (fixture PIN ok). |
| I7 | Win95 TLS still not claimed. |

## Standing process (agents)

When an agent raises this FR / implements it: **that agent UATs and hostile-MRBs back to Bob** (Simon standing order 2026-09-19).

## Acceptance

1. `--chair` prints copy-paste thin command.
2. Skill text matches ritual.
3. pytest/selftest green; no Libera in CI.
4. Originating build agent parks UAT evidence + MRB to Bob.

## Non-goals

- GUI PIN dialog.
- Auto-USB deploy of airc folder.
