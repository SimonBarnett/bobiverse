# FR-C — Wire into Invoke-JeevesMonitorCheck and monitor-start

## Goal
Operators and monitor-start run ticket_closure like other checks.

## Deliverables
- Add `ticket_closure` to `Invoke-JeevesMonitorCheck.ps1` ValidateSet
- List wrapper in AGENTS.md, `bobiverse-jeeves-monitor` SKILL.md, monitor-start
- Existence-lock tests (FR #787 / #954 class)

## Testable
- ValidateSet accepts `ticket_closure`
- Dry-run / wrapper exists on tip after merge
- Existence lock test fails if wrapper missing
