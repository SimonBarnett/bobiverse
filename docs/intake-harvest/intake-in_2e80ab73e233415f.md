What: assigning the automatic variable $pid in a PowerShell script throws on Windows PowerShell 5.1: "Cannot overwrite variable PID because it is read-only or constant." The assignment aborts the statement/loop, so the intended value is lost and the caller errors on every row.
Where: bob/tray/src/Public/Get-BobTrayHover.ps1 had $pid in Get-BobLiveGrokAgents (live grok row never recorded the real process id) and in Get-BobDigestPoolPeriodEnd; bob/tray/src/Private/Invoke-BobGitAccept.ps1 had $pid in Import-BobWorkerGitShop. Seen reviewing PR 8408; pre-existing, not from the hover budget change (FR #8476).
Evidence: Windows PowerShell 5.1 rejects $pid / $PID assignment; pwsh 7 also treats it as read-only constant in strict contexts. grep for "^\s*\$pid\s*=" across bob/tray/src found these three.
Fix/lesson: never name a working variable $pid in PowerShell. Use $procId / $workerPid / $poolId. Pin with a source test that asserts no "^\s*\$pid\s*=" assignment remains (common/tests/test_fr8476_tray_grok_pid_not_readonly.py).
---
_via-intake id=`in_2e80ab73e233415f` ts=`2026-11-20T15:10:10Z`_
_source machine=`redqueen` agent=`Report-BobiverseIntakeIssue` book=`harvest` ver=`-`_
