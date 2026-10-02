function Invoke-BobGrokTalkTick {
    [CmdletBinding()]
    param(
        [string]$Cwd,
        [string]$MachineId
    )

    if (-not $MachineId) {
        try { $MachineId = Get-ThisMachineId } catch { }
    }
    if (-not $Cwd) {
        try { $Cwd = Get-ModuleRoot } catch { $Cwd = (Get-Location).Path }
    }
    $Cwd = [IO.Path]::GetFullPath($Cwd)

    if (Test-BobGrokTalkWorkerBusy) {
        return [pscustomobject]@{ ok = $true; skipped = 'busy'; machine = $MachineId }
    }

    $pending = @(Get-BobGrokTalkPendingJobs -MachineId $MachineId)
    if ($pending.Count -eq 0) {
        return [pscustomobject]@{ ok = $true; skipped = 'empty'; machine = $MachineId }
    }

    if (-not (Test-BobGrokTalkFuelAllowed)) {
        return [pscustomobject]@{
            ok      = $false
            error   = 'no_fuel'
            machine = $MachineId
            job_id  = [string]$pending[0].job_id
            weekly  = (Get-BobGrokTalkWeeklyRemainingPct)
            cursor  = (Get-BobGrokTalkCursorRemainingPct)
        }
    }

    $fuel = Select-BobGrokTalkFuel
    $job = $pending[0]
    $run = Invoke-BobGrokTalkRunJob -Job $job -Fuel $fuel -Cwd $Cwd
    if (-not $run.ok) {
        return [pscustomobject]@{
            ok     = $false
            error  = $run.error
            reason = $run.reason
            job_id = [string]$job.job_id
            fuel   = $fuel
        }
    }
    return [pscustomobject]@{
        ok         = $true
        job_id     = [string]$job.job_id
        fuel       = $fuel
        completion = $run.completion
    }
}
