# Airc UPDATE restart matrix (FR #5277)

**CAST IRON:** after every detached Apply attempt, service **Airc** (or the product service) is **Running**. `{mid}_console` must answer again within **120s** without a human `Start-Service` / NickServ / SCM repair. The live console process never runs inline msiexec (FR #77).

Heal implementation: `Ensure-ServiceRunning -Why apply-finally-heal` in `Invoke-Apply`'s `finally` (`common/scripts/Update-BobiverseService.ps1`). A `return` inside the Apply `try` still runs `finally`.

| Class | Typical cause | Service stopped before exit? | Heal |
|-------|---------------|------------------------------|------|
| `current` | Check already at latest | No (Check does not stop) | N/A; already Running |
| `download-failed` | Get-Asset throw | No | `apply-finally-heal` (idempotent) |
| `stop-failed` | Stop-Service throw | Maybe | `apply-finally-heal` |
| `backup-failed` | robocopy >=8 | Yes (stopped then abort) | catch + `apply-finally-heal` |
| `msiexec-exit` | msiexec not 0/3010/1641 | Yes | rollback + `apply-finally-heal` |
| `msiexec-timeout` | WaitForExit 20 min | Yes (stopped; helper left msiexec) | `apply-finally-heal` (FR #5277 gap close) |
| `apply-skip` | update mutex not held (5s) | No | return before try; service untouched |
| `install-slot-timeout` | MSI mutex 30 min | No | `apply-finally-heal` |
| `rollback` | verify fail after MSI | Yes | `Invoke-Rollback` start + `apply-finally-heal` |

Reconnect budget: **120s** (same as remote-control S5 / parent Success S2).

Failure intake remains FR #5279. VERSION remains FR #5281. Latest-vs-pin remains FR #5280.
