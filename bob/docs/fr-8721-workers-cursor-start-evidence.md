# FR #8721 / BOB-21 evidence: Workers > Cursor starts Cursor CLI

**Issue:** https://github.com/SimonBarnett/bobiverse/issues/8721
**Slice:** Workers > Cursor: start Cursor CLI (Success S1)

## S1

Workers > Cursor starts an explicit Cursor agent; `worker.log` shows a `cursor-agent:` line (cmd path, wrapper PID, nick, workspace).

## How measured

1. BOB-06 already seeds Cursor under Workers in both trays (`AddAgentChoice` / `Update-BobTrayWorkerAgentsMenu`) with `OnAgentChoiceClick` → `StartWorker("agent","cursor")`.
2. After successful `Popen` of a Cursor seat, `bob_worker.py` logs `cursor-agent: cmd=... pid=... nick=... workspace=...`.
3. Line is absent when spawn fails (before/without successful Popen).
4. Tests: `bob/tests/test_fr8721_workers_cursor_start.py`.
5. Live UAT (owner-approved): click Workers > Cursor; capture the log line and a `Win32_Process` descendant whose command line contains `cursor-agent`; post on #8721.

## Fail-when

No start, or no `cursor-agent:` evidence after a successful spawn.

## Test run (fr-8721 worktree)

```
python -m pytest -q bob/tests/test_fr8721_workers_cursor_start.py
# 4 passed
```

# 4 passed
