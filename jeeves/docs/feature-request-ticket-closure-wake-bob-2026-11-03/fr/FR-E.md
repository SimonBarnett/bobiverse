# FR-E — Wake message brief contract

## Goal
Wake text is always actionable for Bob to continue waiting work.

## Deliverables
- Message builder with required fields: repo, number, kind (`issue`|`pr`), state (`closed`|`merged`), continue-waiting cue; optional title
- Shared by ticket_closure / wake adapter

## Testable
- Unit or snapshot tests reject missing id/kind/state
- Example string matches contract
