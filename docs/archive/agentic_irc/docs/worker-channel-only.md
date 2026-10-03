<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/worker-channel-only.md, last changed 2026-09-25. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Worker channel-only output (FR #224)

## Rule

Bob Fleet **worker seats** (`{machine}-{pid}` and legacy `w-<short>-<pid>`) must
publish **all** worker output to their own **`#{machine}`** channel:

- `ACK` / `DONE` / `NACK` / `GIVEUP`
- `!bored`
- replies, status, pong, ordinary seat output
- outbox lines drained by `irc_agent`

They must **never** send `PRIVMSG <nick>` to anyone (including `bob-*`, `simon`,
`Jeeves`, or another worker). There are **no exceptions**.

Implementation: `scripts/channel_only.py` + `Client.send_privmsg_lines` /
`Client.whisper` in `scripts/irc_agent.py` rewrite nick targets to the shop.

## Jeeves `!list` / `!help`

- Typed **in-channel** (`#{machine}`, or `#bobiverse` for simon/bobs) or by PM.
- Jeeves **replies by PM** to the asker (one line per job/command), paced for flood.
- Jeeves posts **nothing** in the channel for those replies.
- Otherwise Jeeves stays **silent** in every `#{machine}` (ACK/DONE listener only).

## Not this rule

- **bob-*** ears may still whisper fleet JSON / `!bobiverse` answers (not worker seats).
- **Jeeves** chair may PM for `!list` / `!help` only.

## Related packages (do not duplicate FRs)

| Repo | Note |
|------|------|
| `agentic_build` | Worker packs / `.grok/skills/bob-mrb-worker`, `bob-irc` should state channel-only; no ear busy/idle IRC status (#341). |
| `AgentMonitor` | `Send-WatchIrcPong` must target the shop channel for worker seats, never a nick. |
| `gh-Jeeves` | G1 / `!help` already PM-only; keep silent shop listener. |

## Hotpatch

Live hotpatch of MarchHare/flamingo seats is **operator-owned** after merge (not
done by PR workers). Preserve queue; do not restart unrelated processes.

## Tests

```bash
pytest -q tests/test_channel_only_fr224.py
```
