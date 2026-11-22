# FR #8760 evidence: build-loop dispatch machine/cwd + live job + capacity

**Issue:** https://github.com/SimonBarnett/bobiverse/issues/8760

## S1 Correct machine+cwd

`Start-BobBuild` validates `cwd` against the **target** machine `fleet/machines/<id>.json` `cwdRoots` (`cwd_not_on_machine` on mismatch). `Select-BobGitWorker -Cwd` skips machines whose roots reject the path.

## S2 Loop watches live job

`Set-BobBuildLoopCurrentJob` / `Get-BobBuildLoopCurrentJob` write `loops/<repo>-<issue>.json` `currentJobId` after inbox enqueue. Build-loop `wait_pr` must read that field (not a cancelled prior job id).

## S3 Dispatch beats park-only

Git job constraints include: issue body `dispatched` wins over older CodeRabbit park-only comments. Helper `Test-BobFrBodyDispatched`.

## S4 Busy-machine visibility

`Select-BobGitWorker` returns `waiting for capacity machine=<id> running=<n>` when the pin/target machine has jobs>0 (error=`capacity`). `Start-BobBuild` surfaces that reason on the wait object.

## Fail-when

Wrong-host cwd enqueue; wait_pr stuck on cancelled job; GIVEUP on park-only after body dispatched; silent wait with no capacity line.
