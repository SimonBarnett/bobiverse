# Wake Grok Bot Bob (FR #6066 / plan FR-D / FR #6391)

On new ticket closures Jeeves detects closes and wakes Bob. Primary transport (FR #6391) is an **HTTPS POST** to a configured Bob wake webhook. Legacy GrokBotApi send remains only when wake is forced without a URL (tests / desktop spike).

## Flow (FR #6391)

| Hop | Where | What |
|-----|-------|------|
| 1. Detect | Jeeves chair (`ChairJobs`, every `TICKET_CLOSURE_S` = 120s) | `ticket_closure.check` polls GitHub Issues API for focused repos (closed issues + PRs since per-repo `poll_cursors`, paginated; legacy `poll_cursor` is the max). Fixture `JEEVES_TICKET_CLOSURE_FIXTURE` is tests-only. |
| 2. Pending | digest ops home | New closes land in `monitor-ticket-closure.json` `pending` (not `seen`). State also holds `last_poll_at`, `last_poll_ok_at`, `last_poll_error`, `poll_outcome`, `last_wake_at`, `pending_count`, `wake_transport` (FR #6400 / #6401). |
| 3. Wake | same chair cycle when URL set | HTTPS POST to `JEEVES_TICKET_CLOSURE_WAKE_URL` / `JEEVES_BOB_WAKE_URL` with brief from `wake_brief.py`. Secret from chair process env `JEEVES_TICKET_CLOSURE_WAKE_SECRET` / `JEEVES_BOB_WAKE_SECRET` only (never logged or written to state). |
| 4. Retry | transport failure | Failed POST stays `pending` with exponential backoff (`wake_unreachable` / `bob_unreachable` / `no_wake_url`). Do **not** mark `seen` on first failure. |

Startup log (chair): `INFO ticket-closure enabled interval=120s wake=webhook|grokbot|disabled`.

`!status` includes a `ticket_closure:` line (last run age, pending, woke, transport, poll outcome, last_ok, err).

## Legacy hand-off (desktop Grok Bot)

When no wake URL is set and `JEEVES_TICKET_CLOSURE_WAKE=1`, `ticket_closure.check` still calls `wake_bob` / `Wake-GrokBotBob.ps1` → `GrokBotApi.py send --agent Bob`. That path is for the desktop spike and tests; fleet installs should configure the HTTPS webhook.

| Hop | Host | What |
|-----|------|------|
| Detect-only | any chair without wake URL/flag | Leaves `pending`; never calls Grok Bot |
| Wake host | Bob Grok Bot desktop | `Wake-GrokBotBob.ps1 -Repo owner/repo -Number N` |

`ticket_closure.check` moves keys to `seen` after a successful wake or a **confirmed** persisted skip for non-transport errors (`ticket-closure-wake-skips.json`, e.g. `invalid_ticket`). If the skip file cannot be written, the key stays `pending`.

**Wake host machine id (legacy):** `BOB_GROK_BOT_WAKE_MACHINE` (stamp `require_machine=<that id>` on wake FIX/FR work). Not `needs-ionos` unless the work is detection-only.

**GrokBotApi.py path:** `GROK_BOT_API` / `BOB_GROK_BOT_API`. Not vendored in bobiverse. Adapter fails closed and redacts tokens.

**CAST IRON:** this wake is not chair `!assign` and never edits `queue.json`.

## Config (fleet)

| Env | Purpose |
|-----|---------|
| `JEEVES_TICKET_CLOSURE_WAKE_URL` / `JEEVES_BOB_WAKE_URL` | HTTPS wake endpoint (preferred) |
| `JEEVES_TICKET_CLOSURE_WAKE_SECRET` / `JEEVES_BOB_WAKE_SECRET` | Bearer / `X-Bob-Wake-Secret` from chair env only (never logged) |
| `JEEVES_TICKET_CLOSURE_WAKE=1` | Force legacy GrokBotApi wake when no URL |
| `JEEVES_TICKET_CLOSURE_FIXTURE` | Test-only event file |

Build: `Build-Jeeves.ps1` hidden-imports `ticket_closure`, `wake_brief`, `wake_grok_bot_bob`.
