function Start-BobBuild {
    [CmdletBinding()]
    param(
        [string]$Machine,
        [string]$Cwd,
        [Parameter(Mandatory)][string]$Goal,
        [string]$Profile = 'generic',
        [string]$From = 'agent',
        [string]$ReplyChannel,
        [string[]]$Constraints,
        [string]$Success = 'Job completes with completion.status=ok',
        [string]$JobId,
        [ValidateSet('git', 'fleet')][string]$Task,
        [ValidateSet('cursor-models', 'grok-build', 'copilot', 'grok-bot', 'on-demand')][string]$Fuel,
        [string]$Repo,
        [string]$Branch,
        [string]$Docs,
        [string]$Plan,
        [string]$Mrb,
        [string]$PrUrl,
        [switch]$AllowOnDemand,
        [switch]$AllowCopilot,
        [string]$Kind = 'build',
        [string]$Model,
        [switch]$Fix,
        [switch]$PinGitWorker,
        [string]$Issue
    )
    if (Test-PromptSecrets -Prompt $Goal) {
        return [pscustomobject]@{ ok = $false; error = 'refuse'; reason = 'goal contains password= or XAI_API_KEY' }
    }
    $null = Get-Profile -Name $Profile
    $isGit = ([string]$Task).ToLowerInvariant() -eq 'git'
    if (-not $isGit -and -not $Machine) {
        return [pscustomobject]@{ ok = $false; error = 'machine_required'; reason = 'Start-BobBuild without -Task git needs -Machine' }
    }
    if (-not $isGit -and -not $Cwd) {
        return [pscustomobject]@{ ok = $false; error = 'cwd_required'; reason = 'Start-BobBuild without -Task git needs -Cwd' }
    }

    $pickMachine = $Machine
    $pickFuel = $Fuel
    if ($isGit) {
        $pinMachine = $Machine
        $pinFuel = $Fuel
        if ($Fix) {
            # FIX re-runs the picker. A full pin (-Machine and -Fuel) still wins.
            if (-not ($Machine -and $Fuel)) {
                $pinMachine = $null
                $pinFuel = $null
                if ($Fuel) { $pinFuel = $Fuel }
            }
        }
        if ($PinGitWorker -and $pinMachine -and $pinFuel) {
            $sel = [pscustomobject]@{ wait = $false; machine = $pinMachine; fuel = $pinFuel; reason = $null }
        }
        else {
            $sel = Select-BobGitWorker -Machine $pinMachine -Fuel $pinFuel -AllowOnDemand:$AllowOnDemand -AllowCopilot:$AllowCopilot -Repo $Repo -Cwd $Cwd -Kind $Kind
        }
        if ($sel.wait) {
            return [pscustomobject]@{
                ok      = $true
                wait    = $true
                jobId   = $(if ($JobId) { $JobId } else { $null })
                reason  = $(if ($sel.reason) { [string]$sel.reason } else { 'no eligible worker' })
                machine = $(if ($sel.machine) { [string]$sel.machine } else { $null })
                fuel    = $(if ($sel.fuel) { [string]$sel.fuel } else { $null })
                lane    = 'wait'
                error   = $(if ($sel.error) { [string]$sel.error } else { $null })
            }
        }
        $pickMachine = [string]$sel.machine
        $pickFuel = [string]$sel.fuel
    }

    $mid = ConvertTo-MachineId $pickMachine
    if (-not $JobId) { $JobId = [guid]::NewGuid().ToString() }
    if ($isGit -and -not $Branch) { $Branch = ('work/{0}' -f $JobId) }

    $cwdVal = $Cwd
    if (-not $cwdVal -and $isGit) {
        $rec = $null
        try {
            $macPath = Join-Path (Initialize-FleetRoot) (Join-Path 'machines' ($mid + '.json'))
            $rec = Read-JsonFile $macPath
        }
        catch { }
        if ($rec -and $rec.cwdRoots -and @($rec.cwdRoots)[0]) { $cwdVal = [string]@($rec.cwdRoots)[0] }
    }
    if (-not $cwdVal) {
        return [pscustomobject]@{ ok = $false; error = 'cwd_required'; reason = 'no Cwd and machine has no cwdRoots' }
    }
    try { $cwdVal = [IO.Path]::GetFullPath($cwdVal) } catch { }

    # FR #8760 S1: cwd must be allowed on the *target* machine cwdRoots (not Wonderland-only paths on ce-priority-dev1).
    $targetRec = $null
    try { $targetRec = Resolve-BobFleetMachineRecord -Machine $mid } catch { }
    if (-not $targetRec) {
        try { $targetRec = Read-JsonFile (Join-Path (Get-BridgeRoot) 'machine.json') } catch { }
    }
    if ($targetRec -and -not (Test-CwdAllowed -Cwd $cwdVal -MachineRecord $targetRec)) {
        return [pscustomobject]@{
            ok      = $false
            error   = 'cwd_not_on_machine'
            reason  = ('cwd not under machine={0} cwdRoots' -f $mid)
            machine = $mid
            cwd     = $cwdVal
        }
    }

    $copilotHint = 'GitHub repo coding: tools/Start-BobCopilot.ps1 (skill start-bob-copilot). Do not use Grok Bot weekly usage for that work.'
    $cons = @($Constraints)
    if ($cons -notcontains $copilotHint) { $cons = @($cons + $copilotHint) }
    if ($isGit) {
        $gitHint = 'Git task: open a PR from the work branch. Never push main. Never merge. IRC verbs SPEC WAIT BUILD PUSH MRB FIX UAT (no vendor names). Do not mark ready for human UAT. Bob chairs UAT. PASS-nits merges; FAIL spawns a FIX worker.'
        if ($cons -notcontains $gitHint) { $cons = @($cons + $gitHint) }
        # FR #8760 S3: body dispatched beats older CodeRabbit park-only comments.
        $dispatchHint = 'Dispatch: if the GitHub issue body contains dispatched (or Feature request ...(dispatched)), implement now. Ignore older CodeRabbit park-only / Do not start until human dispatch comments; the issue body wins.'
        if ($cons -notcontains $dispatchHint) { $cons = @($cons + $dispatchHint) }
        if ($pickFuel -eq 'cursor-models') {
            $curHint = 'Fuel cursor-models: tools/Start-BobCursor.ps1 (skill start-bob-cursor). Do not start grok.exe for this job.'
            if ($cons -notcontains $curHint) { $cons = @($cons + $curHint) }
        }
    }
    if (-not $Task) { $Task = 'fleet' }
    if ($isGit) {
        if (-not $Kind) { $Kind = 'build' }
        $kindErr = Get-BobGitKindValidationError -Kind ([string]$Kind)
        if ($kindErr) {
            return [pscustomobject]@{ ok = $false; error = 'invalid_kind'; reason = $kindErr }
        }
    }
    if (-not $Model) {
        if ($pickFuel -eq 'copilot') { $Model = $null }
        else { $Model = Get-BobJobModel -Kind $Kind -Fuel $pickFuel }
    }
    if (-not $PSBoundParameters.ContainsKey('Fuel') -and -not [string]::IsNullOrWhiteSpace([string]$Model) -and -not $pickFuel) {
        $pickFuel = 'grok-build'
    }
    if ($pickFuel) {
        $fuelModel = Test-BobFuelModelCompatible -Fuel $pickFuel -Model $Model
    }
    else {
        $fuelModel = [pscustomobject]@{ ok = $true; summary = $null }
    }
    if (-not $fuelModel.ok) {
        return [pscustomobject]@{
            ok     = $false
            error  = 'fuel_model_mismatch'
            reason = $fuelModel.summary
            fuel   = $pickFuel
            model  = $Model
        }
    }
    $packet = [pscustomobject]@{
        id             = $JobId
        from           = $From
        to_session     = $JobId
        goal           = $Goal
        constraints    = $cons
        success        = $Success
        reply_channel  = $ReplyChannel
        machine        = $mid
        cwd            = $cwdVal
        profile        = $Profile
        createdAt      = [DateTime]::UtcNow.ToString('o')
        windowsUser    = "$env:USERDOMAIN\$env:USERNAME"
        mssql          = 'integrated'
        task           = $Task
        fuel           = $pickFuel
        repo           = $Repo
        branch         = $Branch
        docs           = $Docs
        plan           = $Plan
        mrb            = $Mrb
        prUrl          = $(if ($PrUrl) { [string]$PrUrl } else { '' })
        kind           = $Kind
        model          = $Model
    }
    $path = Get-FleetJobPath -Lane inbox -Machine $mid -JobId $JobId
    Write-JsonFile $path $packet
    Write-Audit -SessionId $JobId -Cwd $cwdVal -Profile $Profile -Prompt $Goal
    # FR #8760 S2: point build-loop wait_pr at this live job id (not a cancelled prior).
    $issueKey = $Issue
    if (-not $issueKey -and $Goal -match '(?i)(?:issues?|pull)/(\d+)|#(\d+)') {
        $issueKey = $(if ($Matches[1]) { $Matches[1] } else { $Matches[2] })
    }
    if ($isGit -and $issueKey) {
        $repoSlug = 'bobiverse'
        if ($Repo -and $Repo -match '([^/]+)$') { $repoSlug = $Matches[1] }
        try {
            $null = Set-BobBuildLoopCurrentJob -Issue $issueKey -JobId $JobId -Machine $mid -RepoSlug $repoSlug
        } catch { }
    }
    $reply = "queued $JobId on $mid ($Profile)"
    if ($pickFuel) { $reply = "queued $JobId on $mid fuel=$pickFuel ($Profile)" }
    Send-FleetReply -ReplyChannel $ReplyChannel -Text $reply
    return [pscustomobject]@{
        ok      = $true
        wait    = $false
        jobId   = $JobId
        machine = $mid
        fuel    = $pickFuel
        task    = $Task
        path    = $path
        lane    = 'inbox'
        branch  = $Branch
        kind    = $Kind
        model   = $Model
    }
}
