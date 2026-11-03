# Feature request: Jeeves ticket-closure monitor wakes Grok Bot Bob

Repo: `SimonBarnett/bobiverse` (product path `jeeves/` + monitor companions).
Plan folder: `plan/work/plan-20261103-134930`.
Compared tip: `origin/main` @ `597d0f89`.

## Objective

When a Jeeves-watched git ticket (issue or PR) closes, a deterministic monitor notices within one cycle and wakes named Grok Bot **Bob** via `SendGrokBotUserMessage` so Bob unblocks and continues the work he was waiting on — without human polling and without the monitor acting as chair.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Closure detected | Focused/watched-repo issue or PR close appears in monitor JSON `closed[]` within 1 monitor cycle after webhook or github-resync | `jeeves/tools/monitor/ticket_closure.py` fixtures + `pytest`; live `Test-JeevesMonitorTicketClosure.ps1` exit 1 with non-empty `closed[]` | Close known in GitHub or queue purge but check reports empty `closed[]` |
| S2 | Wake once | Each closed id yields exactly one successful `SendGrokBotUserMessage` to agent Bob, or one recorded skip if Bob unreachable | Cursor file `monitor-ticket-closure.json` + unit tests with mocked send; exit codes 0/1/2 | Duplicate wake for same closure key; silent drop with no finding |
| S3 | Brief actionable | Wake text includes `owner/repo#N`, kind (`issue`\|`pr`), state (`closed`\|`merged`), and continue-waiting-work cue | Snapshot / unit tests on message builder in `tests/` | Vague wake text missing id or kind |
| S4 | No chair mutation | ticket_closure / wake path never assigns, focuses, or writes `queue.json` | Hostile pins (string/import) in `jeeves/tests` like other monitor checks | `!assign` or queue writes from these modules |
| S5 | CAST IRON | Gaps filed same turn via intake | `Report-BobiverseIntakeIssue.ps1` | Findings left unfiled |

LOCKED

## Shape

Primary (one): **service**

Hybrid note: Extends existing **ircJeeves** MONITORING companions (`tools/monitor` + PowerShell wrappers). Wake adapter runs on Bob’s Grok Bot desktop host. No TipForm / website UI.

LOCKED

## Stack

Default: Python monitor module under `jeeves/tools/monitor/` (shared `_common.run_check` contract), PowerShell `Test-JeevesMonitorTicketClosure.ps1` + `Invoke-JeevesMonitorCheck.ps1`, GitHub close signals via existing BobCallback `/bob/v1/git` and github-resync, wake via fleet `GrokBotApi.py` `SendGrokBotUserMessage --agent Bob`.

Why: Matches live monitor pattern (exit 0/1/2, one JSON line) and proven Grok Bot API send path (`unstick-grok-bot` / agentic_build tools).

Why-not: Copilot `agents/repos/.../tasks` (wrong notifye); LLM-only polling inside Bob (not deterministic); monitor `!assign` (CAST IRON never act as chair).

LOCKED

## Architecture

```
GitHub issue closed / PR merged|closed
       |
       v
BobCallback /bob/v1/git  (+ github-resync fallback)
       |
       v
queue purge / digest (existing chair path)
       |
       v
ticket_closure.py  (NEW monitor check)
  - read recent closes for focus/resync repos
  - de-dupe via monitor-ticket-closure.json
  - build brief; EXIT 1 when new closes
       |
       +--> JSON finding (observe)
       |
       v
hand-off to Bob desktop host (FR-D spike)
       |
       v
Wake adapter -> GrokBotApi.py send --agent Bob
  SendGrokBotUserMessage (redacted logs)
       |
       v
Grok Bot Bob Temporal turn
  unblocks; continues waiting work
```

Trust: never print Grok Bot tokens, sandbox URLs, or NickServ secrets. Monitor never mutates chair queue. Detection may run on ionos; **wake LOCKED on Bob’s desktop host**.

LOCKED

## Screens

No product UI. Validator HTML stubs document IRC / monitor / Grok Bot surfaces only (not design-uat targets).

| id | file | state |
|----|------|-------|
| M1 | mocks/home.html | primary (status copy) |
| M2 | mocks/empty.html | empty (no recent closes) |
| M3 | mocks/error.html | error (wake failed) |

## Gap vs origin/main (`597d0f89`)

| Area | On tip today | Gap |
|------|----------------|-----|
| `jeeves/tools/monitor/` | health, idle_seats, queue_flow, … no `ticket_closure.py` | Add check |
| `Invoke-JeevesMonitorCheck` ValidateSet | No `ticket_closure` | Wire + existence locks |
| Closed FR purge | `_purge_closed_fr_*` drops rows | Does not wake Bob |
| `copilot_dispatch` | Wakes Copilot cloud tasks | Wrong agent |
| Grok Bot send | Not in bobiverse tree | Adapter + path to `GrokBotApi.py` on desktop host |

## Phase-1 scope (LOCKED)

- Repos: Jeeves-watched / focused / resync set.
- Events: issue **closed**, PR **merged**, PR **closed** (unmerged).
- De-dupe: one wake per closure key.
- No wait registry required (Phase-2 optional).

## UNKNOWN

- Interrupt in-flight Bob turn before send vs send-only (proposal: send always; interrupt only if wedged PENDING).
- Durable home for `GrokBotApi.py` on Bob’s desktop (agentic_build / fleet tools path).
- Exact ionos-detect → desktop-wake hand-off (spike in FR-D).

## LOCKED

- Target repo SimonBarnett/bobiverse; no `gh repo create`
- Notifye Grok Bot Bob; wake via SendGrokBotUserMessage
- Wake host = Bob’s Grok Bot desktop
- Monitor never !assign / queue edit
- Anti-omnibus small FRs (see SMALL-FRS.tsv)
- Plan harvest how-to-plan only to skills-visionary

## Small FR index

See `SMALL-FRS.tsv` and `fr/FR-A.md` … `FR-G.md` drafts. Unfiled until operator **approve park**.

