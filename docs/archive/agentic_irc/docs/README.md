<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/README.md, last changed 2026-09-29. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# docs/ index

Agents: open **live** specs below. Do not treat `mrb-*.md` / `mrb-*.pdf` as current product spec — they are hostile MRB audit history.

## Live (current)

| Doc | Role |
|---|---|
| `feature-request-bob-listen-talk-all-seats-2026-09-21.md` | Every `bob-*` ACK on @mention / Query (no grok.exe) — merged PR #54 |
| `build-and-test-plan-bob-listen-talk-all-seats-2026-09-21.md` | Worker plan for listen/talk ACK |
| `feature-request-bob-grok-irc-listen-talk-2026-09-21.md` | Optional Grok/LLM listen-talk on @mention (sister `agentic_build`) |
| `build-and-test-plan-bob-grok-irc-listen-talk-2026-09-21.md` | Worker plan for grok-talk hook |
| `feature-request-shop-channel-worker-cc-webhook-2026-09-21.md` | Shop channels, pid workers, write-only callback, `!bobiverse` only (issue #46) |
| `build-and-test-plan-shop-channel-worker-cc-webhook-2026-09-21.md` | Worker plan for #46 |
| `feature-request-house-clean-irc-kit-2026-09-21.md` | Fleet canon alignment (issue #34) |
| `multi-agent-one-host.md` | Two `--home` dirs; Ergo vs legacy Libera |
| `prior-irc-clean.md` | Deterministic kill of crashed `irc_agent` / `irc_listen` priors before connect |
| `beacon-v1-2026-09-19.md` | Mode 3 zero-config invite / `beacon.url` |
| `mode3-dumb-ops.md` | DUMB exec jail, operators, paths |
| `build-and-test-plan-house-clean-irc-kit-2026-09-21.md` | Worker plan for #34 |
| `feature-request-ionos-shop-channel-bob-ionos-2026-09-21.md` | `#ionos` shop for `bob-ionos` + `w-io-*` (issue #70) |
| `build-and-test-plan-ionos-shop-channel-bob-ionos-2026-09-21.md` | Worker plan for #70 |
| `bobiverse-ionos-ircd.md` | Ergo `#ionos` operator note + sister bobiverse.md cross-link |
| `ergo-chanserv-enable-bob-shops.md` | **ionos action:** enable ChanServ + bob-* REGISTER `#{machine}` (FR #313) |
| `feature-request-bob-chanserv-register-shop-2026-09-29.md` | FR #313 — bob REGISTER shop with ChanServ |
| `tofu-rotation.md` | AGPK pin mistakes and key rotation drill |
| `watch-agent-health-aider.md` | Watch-AgentHealth `-Aider` live REPL wake (after Start-TalkSeat) |
| `build-and-test-plan-watch-agent-health-aider-2026-09-24.md` | Worker plan for Aider watcher |

`feature-request-report-bobiverse-digest-2026-09-21.md` (#36) is historical for the
**write** path (`!report` scrubbed). `!bobiverse` as whisper-JSON reader is kept and
redefined in the shop-channel FR.

Fleet host, channel, and nick table: **`agentic_build/docs/bobiverse.md`** and **`agentic_build/config/bobiverse.json`** (not duplicated here).

## Historical (audit only)

`mrb-*.md` and matching PDFs record past hostile MRB verdicts (mode1/2/3, invite-airc, dotnet backlog). Useful for humans tracing decisions; **not** the spec to implement from.

Older feature requests (`feature-request-*.md`) stay for traceability; prefer the dated FR that matches the open GitHub issue.
