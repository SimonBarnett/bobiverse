# FR-D — Wake adapter to Grok Bot Bob (desktop host)

## Goal
On new closures, send one redacted wake message to named Grok Bot Bob via cloud API.

## Deliverables
- Wake script (e.g. `Wake-GrokBotBob.ps1` or Python) wrapping `GrokBotApi.py send --agent Bob --text …`
- Spike note: how ionos detection hands off to Bob’s desktop host
- Fail closed: unreachable Bob → finding, no secret leak
- `require_machine` for Bob’s desktop machine id on wake work

## Testable
- Mocked send called once; brief contains `owner/repo#N`
- Logs contain no token / sandbox URL
- Documented hand-off path in jeeves/docs (or UNKNOWN with spike evidence)
