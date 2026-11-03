# Wake Grok Bot Bob (FR #6066 / plan FR-D)

On new ticket closures the detect host (often **ionos**, `ticket_closure` monitor) must not call Grok Bot itself. Wake is LOCKED to **Bob's Grok Bot desktop**.

## Hand-off (spike)

| Hop | Host | What |
|-----|------|------|
| 1. Detect | ionos (or any chair/monitor box) | `ticket_closure` finding with `closed[]` (`owner/repo#N`) |
| 2. Hand-off | ionos → wake host | Copy the closed id (shop line / job file). Do **not** `!assign` |
| 3. Wake | Bob Grok Bot desktop | `Wake-GrokBotBob.ps1 -Repo owner/repo -Number N` → `GrokBotApi.py send --agent Bob --text …` (`SendGrokBotUserMessage`) |

**Wake host machine id:** `BOB_GROK_BOT_WAKE_MACHINE` (stamp `require_machine=<that id>` on wake FIX/FR work). Not `needs-ionos` unless the work is detection-only.

**GrokBotApi.py path:** `GROK_BOT_API` / `BOB_GROK_BOT_API`. Not vendored in bobiverse (UNKNOWN durable home: agentic_build / fleet tools on the desktop). Adapter fails closed (`bob_unreachable` / missing script) and redacts tokens and sandbox URLs.

**CAST IRON:** this wake is not chair `!assign` and never edits `queue.json`.
