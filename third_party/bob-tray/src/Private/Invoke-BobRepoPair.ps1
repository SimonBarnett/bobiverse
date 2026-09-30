function Get-BobRepoPairStatePath {
    Join-Path (Get-BridgeRoot) 'repo-pair.json'
}

function Get-BobRepoPairIdleSec {
    if ($env:BOB_REPO_PAIR_IDLE_SEC -and $env:BOB_REPO_PAIR_IDLE_SEC.Trim()) {
        try { return [int]$env:BOB_REPO_PAIR_IDLE_SEC } catch { }
    }
    return 300
}

function Read-BobRepoPairState {
    $p = Get-BobRepoPairStatePath
    $o = Read-JsonFile $p
    if (-not $o) { return $null }
    if (-not $o.seats) {
        $o | Add-Member -NotePropertyName seats -NotePropertyValue ([pscustomobject]@{}) -Force
    }
    return $o
}

function Write-BobRepoPairState {
    param($State)
    if (-not $State) { return }
    $State | Add-Member -NotePropertyName updatedAt -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
    Write-JsonFile (Get-BobRepoPairStatePath) $State
}

function Get-BobShopChannelForMachine {
    param([string]$MachineId)
    $mid = $MachineId
    if (-not $mid) { $mid = Get-ThisMachineId }
    if (-not $mid) { return $null }
    if ([string]$mid -eq 'ce-priority-dev1') { return '#ce-priority-dev1' }
    return ('#' + [string]$mid)
}

function Get-BobRepoPairShopNickShort {
    param([string]$MachineId)
    switch ([string]$MachineId) {
        'ionos' { return 'io' }
        'flamingo' { return 'fl' }
        'marchhare' { return 'mh' }
        'ce-priority-dev1' { return 'd1' }
        default {
            $s = [string]$MachineId
            if ($s.Length -ge 2) { return $s.Substring(0, 2) }
            return 'w'
        }
    }
}

function New-BobRepoPairSeat {
    param(
        [Parameter(Mandatory)][ValidateSet('dev', 'mrb')][string]$Role,
        [string]$SessionId,
        [string]$WorkingOn
    )
    $now = [DateTime]::UtcNow.ToString('o')
    return [pscustomobject]@{
        role              = $Role
        sessionId         = $SessionId
        workingOn         = $WorkingOn
        lastActiveAt      = $now
        idleSince         = $null
        implementedPrUrl  = $null
        activeSha         = $null
        lastComplete      = $null
    }
}

function Build-BobRepoPairWorkerPrompt {
    param(
        [Parameter(Mandatory)][ValidateSet('dev', 'mrb')][string]$Role,
        [Parameter(Mandatory)][string]$Repo
    )
    $rules = Get-BobRepoPairRulesText -Role $Role
    if ($Role -eq 'dev') {
        return @(
            "You are the persistent DEV worker for repo $Repo on this machine shop."
            $rules
            'JOIN the machine shop IRC channel now (bob-irc skill). Never join #bobiverse.'
            'Implement git tasks and open PRs. Never push main. Never merge.'
            'After you open a PR, register dev complete; the MRB seat hostile-reviews it; you take the next PR.'
            'Do not put secrets or API key assignments in git or prompts.'
        ) -join ' '
    }
    return @(
        "You are the persistent MRB worker for repo $Repo on this machine shop."
        $rules
        'JOIN the machine shop IRC channel now (bob-irc skill). Never join #bobiverse.'
        'Hostile MRB only — never implement the same PR you review.'
        'PASS-nits may merge per existing rule; FAIL means the dev seat FIXes, then you re-MRB.'
        'Do not put secrets or API key assignments in git or prompts.'
    ) -join ' '
}

function Get-BobRepoPairSeatWorkerEntry {
    param($Seat)
    if (-not $Seat -or -not $Seat.sessionId) { return $null }
    $sid = [string]$Seat.sessionId
    foreach ($w in @(Get-BobWorkers)) {
        if ([string]$w.sessionId -eq $sid) { return $w }
    }
    return $null
}

function Test-BobRepoPairSeatProcessResponding {
    param(
        [Parameter(Mandatory)][string]$SessionId,
        [int]$MaxHeartbeatAgeSec = 120
    )
    $statusPath = Join-Path (Get-WorkerDir $SessionId) 'status.json'
    $status = Read-JsonFile $statusPath
    if (-not $status) { return $false }
    $pidVal = $null
    if ($status.agentPid) { $pidVal = $status.agentPid }
    elseif ($status.pid) { $pidVal = $status.pid }
    if (-not $pidVal) { return $false }
    if ($pidVal -is [System.Array]) { $pidVal = @($pidVal)[0] }
    $proc = Get-Process -Id ([int]$pidVal) -ErrorAction SilentlyContinue
    if (-not $proc) { return $false }
    $hbPath = Join-Path (Get-WorkerDir $SessionId) 'heartbeat.json'
    if (Test-Path $hbPath) {
        try {
            $hb = Read-JsonFile $hbPath
            if ($hb -and $hb.agentPid) {
                $ap = $hb.agentPid
                if ($ap -is [System.Array]) { $ap = @($ap)[0] }
                $agentProc = Get-Process -Id ([int]$ap) -ErrorAction SilentlyContinue
                if (-not $agentProc) { return $false }
            }
            if ($hb -and $hb.at) {
                $at = [DateTime]::Parse([string]$hb.at, $null, [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
                $age = ([DateTime]::UtcNow - $at).TotalSeconds
                if ($age -gt $MaxHeartbeatAgeSec) { return $false }
            }
        }
        catch { return $false }
    }
    return $true
}

function Test-BobRepoPairSeatShopJoined {
    param($WorkerEntry, [string]$SessionId)
    if (-not $WorkerEntry) { return $false }
    $sid = $SessionId
    if (-not $sid -and $WorkerEntry.sessionId) { $sid = [string]$WorkerEntry.sessionId }
    if (-not $sid) { return $false }
    $home = Get-BobIrcHome
    if (-not $home) { return $false }
    $manifestPath = Join-Path $home ('shop-join-' + $sid + '.json')
    if (-not (Test-Path -LiteralPath $manifestPath)) { return $false }
    $manifest = Read-JsonFile $manifestPath
    if (-not $manifest) { return $false }
    $jk = [string]$manifest.joinKind
    if ($jk -eq 'irc_agent_stub' -or $jk -match 'stub') { return $false }
    if ($jk -notmatch '^(irc_agent|irc_agent_worker)$') { return $false }
    if ($manifest.shopNickLive -eq $false) { return $false }
    $ircPid = $manifest.ircAgentPid
    if (-not $ircPid) { return $false }
    if ($ircPid -is [System.Array]) { $ircPid = @($ircPid)[0] }
    return ($null -ne (Get-Process -Id ([int]$ircPid) -ErrorAction SilentlyContinue))
}

function Test-BobRepoPairSeatAlive {
    param($Seat)
    $w = Get-BobRepoPairSeatWorkerEntry -Seat $Seat
    if (-not $w) { return $false }
    if ([string]$w.kind -ne 'persistent') { return $false }
    if (-not (Test-BobRepoPairSeatProcessResponding -SessionId ([string]$w.sessionId))) { return $false }
    if (-not (Test-BobRepoPairSeatShopJoined -WorkerEntry $w -SessionId ([string]$w.sessionId))) { return $false }
    return $true
}

function Ensure-BobRepoPairSeat {
    param(
        $State,
        [Parameter(Mandatory)][ValidateSet('dev', 'mrb')][string]$Role,
        [Parameter(Mandatory)][string]$Cwd,
        [Parameter(Mandatory)][string]$Repo,
        [switch]$RegisterOnly
    )
    $seat = $null
    if ($State.seats -and $State.seats.$Role) { $seat = $State.seats.$Role }
    if ($seat -and (Test-BobRepoPairSeatAlive -Seat $seat)) {
        return $seat
    }
    $mid = [string]$State.machineId
    if (-not $mid) { $mid = Get-ThisMachineId }
    $short = Get-BobRepoPairShopNickShort -MachineId $mid
    $title = ('w-{0}-{1}' -f $short, $Role)
    $shopNick = $title
    $shopChannel = Get-BobShopChannelForMachine -MachineId $mid
    $sid = [guid]::NewGuid().ToString()
    if (-not $RegisterOnly) {
        $r = Start-BobRepoPairWorker -Role $Role -Cwd $Cwd -Repo $Repo -Title $title -SessionId $sid -ShopNick $shopNick -ShopChannel $shopChannel
        if (-not $r.ok) {
            return [pscustomobject]@{ ok = $false; error = 'spawn_failed'; reason = $(if ($r.reason) { $r.reason } else { $r.error }); role = $Role }
        }
        if ($r.sessionId) { $sid = [string]$r.sessionId }
    }
    $seat = New-BobRepoPairSeat -Role $Role -SessionId $sid -WorkingOn $(if ($Role -eq 'dev') { 'dev idle' } else { 'mrb idle' })
    if (-not $State.seats -or ($State.seats -is [hashtable]) -or ($State.seats -is [System.Collections.Specialized.OrderedDictionary])) {
        $State | Add-Member -NotePropertyName seats -NotePropertyValue (New-Object PSObject) -Force
    }
    $State.seats | Add-Member -NotePropertyName $Role -NotePropertyValue $seat -Force
    return $seat
}

function Start-BobRepoPair {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Repo,
        [Parameter(Mandatory)][string]$Cwd,
        [string]$MachineId,
        [switch]$RegisterOnly
    )
    $repo = [string]$Repo.Trim()
    if (-not $repo) {
        return [pscustomobject]@{ ok = $false; error = 'bad_repo' }
    }
    $cwdFull = [IO.Path]::GetFullPath($Cwd)
    $mid = $MachineId
    if (-not $mid) { $mid = Get-ThisMachineId }
    $prev = Read-BobRepoPairState
    if ($prev -and [string]$prev.repo -and [string]$prev.repo -ne $repo) {
        Set-BobShopChannelRepoDescription -Repo $repo -MachineId $mid | Out-Null
    }
    $state = [pscustomobject]@{
        repo      = $repo
        cwd       = $cwdFull
        machineId = $mid
        seats     = (New-Object PSObject)
    }
    if ($prev -and [string]$prev.repo -eq $repo -and $prev.seats) {
        $state.seats = $prev.seats
    }
    $dev = Ensure-BobRepoPairSeat -State $state -Role dev -Cwd $cwdFull -Repo $repo -RegisterOnly:$RegisterOnly
    if ($dev.error) { return [pscustomobject]@{ ok = $false; error = $dev.error; reason = $dev.reason; role = 'dev' } }
    $mrb = Ensure-BobRepoPairSeat -State $state -Role mrb -Cwd $cwdFull -Repo $repo -RegisterOnly:$RegisterOnly
    if ($mrb.error) { return [pscustomobject]@{ ok = $false; error = $mrb.error; reason = $mrb.reason; role = 'mrb' } }
    Write-BobRepoPairState $state
    Set-BobShopChannelRepoDescription -Repo $repo -MachineId $mid | Out-Null
    Sync-BobChannelOpsManifest -MachineId $mid | Out-Null
    return [pscustomobject]@{
        ok    = $true
        repo  = $repo
        cwd   = $cwdFull
        dev   = $dev
        mrb   = $mrb
        state = $state
    }
}

function Get-BobRepoPair {
    [CmdletBinding()]
    param()
    $s = Read-BobRepoPairState
    if (-not $s) {
        return [pscustomobject]@{ ok = $false; error = 'none' }
    }
    return [pscustomobject]@{ ok = $true; pair = $s }
}

function Touch-BobRepoPairSeat {
    param(
        [Parameter(Mandatory)][ValidateSet('dev', 'mrb')][string]$Seat,
        [string]$WorkingOn
    )
    $s = Read-BobRepoPairState
    if (-not $s -or -not $s.seats -or -not $s.seats.$Seat) { return $null }
    $row = $s.seats.$Seat
    $now = [DateTime]::UtcNow.ToString('o')
    $row | Add-Member -NotePropertyName lastActiveAt -NotePropertyValue $now -Force
    $row | Add-Member -NotePropertyName idleSince -NotePropertyValue $null -Force
    if ($WorkingOn) { $row | Add-Member -NotePropertyName workingOn -NotePropertyValue ([string]$WorkingOn) -Force }
    Write-BobRepoPairState $s
    return $row
}

function Update-BobRepoWorkerWorkingOn {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][ValidateSet('dev', 'mrb')][string]$Seat,
        [Parameter(Mandatory)][string]$Description
    )
    if (Test-PromptSecrets -Prompt $Description) {
        return [pscustomobject]@{ ok = $false; error = 'refuse'; reason = 'description contains secrets pattern' }
    }
    $row = Touch-BobRepoPairSeat -Seat $Seat -WorkingOn $Description
    if (-not $row) {
        return [pscustomobject]@{ ok = $false; error = 'no_pair' }
    }
    $s = Read-BobRepoPairState
    $post = Invoke-BobDigestWebhookPost -WorkingOn $Description -Repo $(if ($s.repo) { [string]$s.repo } else { $null })
    return [pscustomobject]@{
        ok         = $true
        seat       = $Seat
        working_on = $Description
        webhook    = $post
    }
}

function Register-BobRepoPairDevComplete {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$PrUrl,
        [string]$Sha
    )
    $s = Read-BobRepoPairState
    if (-not $s -or -not $s.seats -or -not $s.seats.dev) {
        return [pscustomobject]@{ ok = $false; error = 'no_pair' }
    }
    $dev = $s.seats.dev
    $dev | Add-Member -NotePropertyName implementedPrUrl -NotePropertyValue ([string]$PrUrl) -Force
    $dev | Add-Member -NotePropertyName activeSha -NotePropertyValue $null -Force
    $dev | Add-Member -NotePropertyName lastComplete -NotePropertyValue 'dev_complete' -Force
    $dev | Add-Member -NotePropertyName workingOn -NotePropertyValue ('dev complete ' + $PrUrl) -Force
    $dev | Add-Member -NotePropertyName lastActiveAt -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
    Write-BobRepoPairState $s
    Update-BobRepoWorkerWorkingOn -Seat dev -Description ('dev complete ' + $PrUrl) | Out-Null
    return [pscustomobject]@{ ok = $true; prUrl = $PrUrl; sha = $Sha }
}

function Register-BobRepoPairMrbComplete {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$PrUrl,
        [ValidateSet('PASS-nits', 'PASS', 'FAIL')][string]$Verdict = 'PASS-nits'
    )
    $guard = Test-BobRepoPairSelfMrb -Seat mrb -PrUrl $PrUrl
    if (-not $guard.allowed) {
        return [pscustomobject]@{ ok = $false; error = 'self_mrb_blocked'; reason = $guard.reason }
    }
    $s = Read-BobRepoPairState
    if (-not $s -or -not $s.seats -or -not $s.seats.mrb) {
        return [pscustomobject]@{ ok = $false; error = 'no_pair' }
    }
    $mrb = $s.seats.mrb
    $tag = 'mrb_complete'
    if ($Verdict -eq 'FAIL') { $tag = 'mrb_fail' }
    $mrb | Add-Member -NotePropertyName lastComplete -NotePropertyValue $tag -Force
    $mrb | Add-Member -NotePropertyName workingOn -NotePropertyValue ("$tag $PrUrl") -Force
    $mrb | Add-Member -NotePropertyName lastActiveAt -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
    Write-BobRepoPairState $s
    Update-BobRepoWorkerWorkingOn -Seat mrb -Description ("$tag $PrUrl") | Out-Null
    return [pscustomobject]@{ ok = $true; prUrl = $PrUrl; verdict = $Verdict }
}

function Test-BobRepoPairSelfMrb {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][ValidateSet('dev', 'mrb')][string]$Seat,
        [Parameter(Mandatory)][string]$PrUrl
    )
    $s = Read-BobRepoPairState
    if (-not $s -or -not $s.seats) {
        if ($Seat -eq 'mrb') {
            return [pscustomobject]@{ ok = $true; allowed = $false; reason = 'no_pair_state' }
        }
        return [pscustomobject]@{ ok = $true; allowed = $true; reason = 'no_pair_state' }
    }
    $impl = $null
    if ($s.seats.dev -and $s.seats.dev.implementedPrUrl) {
        $impl = [string]$s.seats.dev.implementedPrUrl
    }
    if (-not $impl) {
        if ($Seat -eq 'mrb') {
            return [pscustomobject]@{ ok = $true; allowed = $false; reason = 'no_implementer_pr' }
        }
        return [pscustomobject]@{ ok = $true; allowed = $true; reason = 'no_implementer_pr' }
    }
    $same = ($impl -eq [string]$PrUrl)
    if ($Seat -eq 'dev' -and $same) {
        return [pscustomobject]@{ ok = $true; allowed = $false; reason = 'implementer_cannot_mrb_own_pr' }
    }
    if ($Seat -eq 'mrb' -and $same) {
        return [pscustomobject]@{ ok = $true; allowed = $true; reason = 'mrb_seat_reviews_implementer_pr' }
    }
    if ($Seat -eq 'mrb') {
        return [pscustomobject]@{ ok = $true; allowed = $false; reason = 'mrb_seat_must_review_implementer_pr' }
    }
    return [pscustomobject]@{ ok = $true; allowed = $true; reason = 'different_pr' }
}

function Start-BobRepoPairMrbReview {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$PrUrl,
        [string]$Task
    )
    $guard = Test-BobRepoPairSelfMrb -Seat mrb -PrUrl $PrUrl
    if (-not $guard.allowed) {
        return [pscustomobject]@{ ok = $false; error = 'self_mrb_blocked'; reason = $guard.reason }
    }
    $taskText = $Task
    if (-not $taskText) { $taskText = "hostile MRB $PrUrl" }
    return Assign-BobRepoPairTask -Seat mrb -Task $taskText -PrUrl $PrUrl
}

function Deliver-BobRepoPairChairInbox {
    param(
        [Parameter(Mandatory)][ValidateSet('dev', 'mrb')][string]$Seat,
        [Parameter(Mandatory)][string]$Task,
        [string]$PrUrl
    )
    $s = Read-BobRepoPairState
    if (-not $s -or -not $s.seats -or -not $s.seats.$Seat) { return }
    $row = $s.seats.$Seat
    if (-not $row.sessionId) { return }
    $dir = Get-WorkerDir ([string]$row.sessionId)
    $inboxDir = Join-Path $dir 'inbox'
    New-Item -ItemType Directory -Force -Path $inboxDir | Out-Null
    $body = [string]$Task
    if ($PrUrl) { $body = ($body + "`n" + $PrUrl) }
    [IO.File]::WriteAllText((Join-Path $inboxDir 'chair-task.txt'), $body)
    $prompt = @{
        seat    = $Seat
        task    = [string]$Task
        prUrl   = $(if ($PrUrl) { [string]$PrUrl } else { $null })
        sentAt  = [DateTime]::UtcNow.ToString('o')
    }
    Write-JsonFile (Join-Path $inboxDir 'chair-prompt.json') $prompt
}

function Assign-BobRepoPairTask {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][ValidateSet('dev', 'mrb')][string]$Seat,
        [Parameter(Mandatory)][string]$Task,
        [string]$PrUrl,
        [switch]$SkipWorkingOnPost
    )
    $s = Read-BobRepoPairState
    if (-not $s -or -not $s.seats -or -not $s.seats.$Seat) {
        return [pscustomobject]@{ ok = $false; error = 'no_pair' }
    }
    if ($Seat -eq 'mrb' -and $PrUrl) {
        $guard = Test-BobRepoPairSelfMrb -Seat $Seat -PrUrl $PrUrl
        if (-not $guard.allowed) {
            return [pscustomobject]@{ ok = $false; error = 'self_mrb_blocked'; reason = $guard.reason }
        }
    }
    elseif ($PrUrl) {
        $guard = Test-BobRepoPairSelfMrb -Seat $Seat -PrUrl $PrUrl
        if (-not $guard.allowed) {
            if ($Seat -eq 'dev' -or $Task -match '(?i)mrb|review') {
                return [pscustomobject]@{ ok = $false; error = 'self_mrb_blocked'; reason = $guard.reason }
            }
        }
    }
    $row = $s.seats.$Seat
    $row | Add-Member -NotePropertyName chairTask -NotePropertyValue ([string]$Task) -Force
    if ($PrUrl) { $row | Add-Member -NotePropertyName chairPrUrl -NotePropertyValue ([string]$PrUrl) -Force }
    Write-BobRepoPairState $s
    Deliver-BobRepoPairChairInbox -Seat $Seat -Task $Task -PrUrl $PrUrl
    if (-not $SkipWorkingOnPost) {
        Update-BobRepoWorkerWorkingOn -Seat $Seat -Description ([string]$Task) | Out-Null
        $s = Read-BobRepoPairState
        $row = $s.seats.$Seat
        $row | Add-Member -NotePropertyName lastActiveAt -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
        $row | Add-Member -NotePropertyName idleSince -NotePropertyValue $null -Force
        Write-BobRepoPairState $s
    }
    return [pscustomobject]@{ ok = $true; seat = $Seat; task = $Task; prUrl = $PrUrl }
}

function Test-BobRepoPairMayEnqueueBuild {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Sha)
    $s = Read-BobRepoPairState
    if (-not $s -or -not $s.seats -or -not $s.seats.dev) {
        return [pscustomobject]@{ ok = $true; allowed = $true }
    }
    $active = $null
    if ($s.seats.dev.activeSha) { $active = [string]$s.seats.dev.activeSha }
    if ($active -and $active -ne [string]$Sha) {
        return [pscustomobject]@{ ok = $true; allowed = $true; reason = 'different_sha' }
    }
    if ($active -and $active -eq [string]$Sha) {
        return [pscustomobject]@{ ok = $true; allowed = $false; reason = 'dev_already_building_sha' }
    }
    return [pscustomobject]@{ ok = $true; allowed = $true }
}

function Set-BobRepoPairDevActiveSha {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Sha)
    $s = Read-BobRepoPairState
    if (-not $s -or -not $s.seats -or -not $s.seats.dev) {
        return [pscustomobject]@{ ok = $false; error = 'no_pair' }
    }
    $check = Test-BobRepoPairMayEnqueueBuild -Sha $Sha
    if (-not $check.allowed) {
        return [pscustomobject]@{ ok = $false; error = 'duplicate_build'; reason = $check.reason }
    }
    $s.seats.dev | Add-Member -NotePropertyName activeSha -NotePropertyValue ([string]$Sha) -Force
    Write-BobRepoPairState $s
    return [pscustomobject]@{ ok = $true; sha = $Sha }
}

function Invoke-BobRepoPairTick {
    [CmdletBinding()]
    param()
    $s = Read-BobRepoPairState
    if (-not $s -or -not $s.repo -or -not $s.cwd) {
        return [pscustomobject]@{ ok = $true; idleStop = @(); restarted = @() }
    }
    $idleSec = Get-BobRepoPairIdleSec
    $stopped = @()
    $restarted = @()
    foreach ($role in @('dev', 'mrb')) {
        $seat = $s.seats.$role
        if (-not $seat) {
            $fresh = Ensure-BobRepoPairSeat -State $s -Role $role -Cwd ([string]$s.cwd) -Repo ([string]$s.repo)
            if ($fresh -and -not $fresh.error) { $restarted += $role }
            continue
        }
        $alive = Test-BobRepoPairSeatAlive -Seat $seat
        if (-not $alive) {
            if ($seat.sessionId) {
                Stop-BobWorker -SessionId ([string]$seat.sessionId) | Out-Null
                $seat | Add-Member -NotePropertyName sessionId -NotePropertyValue $null -Force
            }
            $respawn = Ensure-BobRepoPairSeat -State $s -Role $role -Cwd ([string]$s.cwd) -Repo ([string]$s.repo)
            if ($respawn -and -not $respawn.error) { $restarted += $role }
            continue
        }
        $last = $null
        if ($seat.lastActiveAt) {
            try { $last = [DateTime]::Parse([string]$seat.lastActiveAt, $null, [Globalization.DateTimeStyles]::RoundtripKind) } catch { }
        }
        if (-not $last) { continue }
        $age = ([DateTime]::UtcNow - $last.ToUniversalTime()).TotalSeconds
        if ($age -lt $idleSec) {
            $seat | Add-Member -NotePropertyName idleSince -NotePropertyValue $null -Force
            continue
        }
        if ($seat.sessionId) {
            Stop-BobWorker -SessionId ([string]$seat.sessionId) | Out-Null
            $stopped += $role
            $seat | Add-Member -NotePropertyName sessionId -NotePropertyValue $null -Force
        }
    }
    if ($stopped.Count -gt 0 -or $restarted.Count -gt 0) { Write-BobRepoPairState $s }
    return [pscustomobject]@{ ok = $true; idleStop = @($stopped); restarted = @($restarted) }
}

function Get-BobShopChannelDescriptionsPath {
    Join-Path (Get-BobIrcHome) 'shop-channel-descriptions.json'
}

function Get-BobChannelOpsConfigPath {
    Join-Path (Get-ModuleRoot) 'config\channel-ops.json'
}

function Sync-BobChannelOpsManifest {
    [CmdletBinding()]
    param([string]$MachineId)
    $path = Get-BobChannelOpsConfigPath
    if (-not (Test-Path $path)) { return [pscustomobject]@{ ok = $false; error = 'no_config' } }
    $cfg = Read-JsonFile $path
    if (-not $cfg -or -not $cfg.channels) { return [pscustomobject]@{ ok = $false; error = 'bad_config' } }
    $home = Get-BobIrcHome
    if (-not $home) { return [pscustomobject]@{ ok = $false; error = 'no_irc_home' } }
    New-Item -ItemType Directory -Force -Path $home | Out-Null
    $mid = $MachineId
    if (-not $mid) { $mid = Get-ThisMachineId }
    $shop = Get-BobShopChannelForMachine -MachineId $mid
    $map = @{}
    foreach ($p in $cfg.channels.PSObject.Properties) {
        $map[[string]$p.Name] = [string]$p.Value
    }
    if ($shop -and -not $map.ContainsKey($shop)) {
        $nick = $null
        try {
            $bv = Get-BobiverseConfig
            if ($bv -and $bv.nicks -and $bv.nicks.$mid) { $nick = [string]$bv.nicks.$mid }
        }
        catch { }
        if ($nick) { $map[$shop] = $nick }
    }
    Write-JsonFile (Join-Path $home 'channel-ops.json') ([pscustomobject]$map)
    try { Sync-BobIrcChannelOpsWire | Out-Null } catch { }
    return [pscustomobject]@{ ok = $true; path = (Join-Path $home 'channel-ops.json') }
}

function Sync-BobShopChannelRepoDescriptions {
    [CmdletBinding()]
    param()
    $home = Get-BobIrcHome
    if (-not $home) { return [pscustomobject]@{ ok = $false; error = 'no_irc_home' } }
    $pending = Join-Path $home 'pending-shop-topic.txt'
    if (-not (Test-Path $pending)) {
        return [pscustomobject]@{ ok = $true; applied = @() }
    }
    $map = @{}
    $descPath = Get-BobShopChannelDescriptionsPath
    $existing = Read-JsonFile $descPath
    if ($existing) {
        foreach ($p in $existing.PSObject.Properties) { $map[[string]$p.Name] = [string]$p.Value }
    }
    $applied = @()
    foreach ($line in @(Get-Content -LiteralPath $pending -ErrorAction SilentlyContinue)) {
        $t = ([string]$line).Trim()
        if (-not $t) { continue }
        $parts = $t.Split("`t", 2)
        if ($parts.Count -lt 2) { continue }
        $chan = [string]$parts[0].Trim()
        $repo = [string]$parts[1].Trim()
        if (-not $chan -or -not $repo) { continue }
        $prev = $null
        if ($map.ContainsKey($chan)) { $prev = $map[$chan] }
        if ($prev -eq $repo) { continue }
        $map[$chan] = $repo
        $applied += ,[pscustomobject]@{ channel = $chan; repo = $repo }
        Add-BobIrcOutboxChannelLine ("SHOPDESC $chan $repo")
        Add-BobIrcOutboxChannelLine ("TOPIC $chan :$repo")
    }
    if ($applied.Count -gt 0) {
        Write-JsonFile $descPath ([pscustomobject]$map)
    }
    return [pscustomobject]@{ ok = $true; applied = @($applied) }
}

function Invoke-BobRepoPairOutstandingTickets {
    [CmdletBinding()]
    param()
    $s = Read-BobRepoPairState
    if (-not $s -or -not $s.repo) {
        return [pscustomobject]@{ ok = $false; error = 'no_pair' }
    }
    $repo = [string]$s.repo
    $issues = @()
    $gh = $env:BOB_GH_EXE
    if (-not $gh) { $gh = 'gh' }
    if ($env:BOB_FAKE_GH_MODE) {
        $fixture = Join-Path (Get-BridgeRoot) 'fake-gh-open-issues.json'
        if (Test-Path $fixture) {
            try { $issues = @(Get-Content $fixture -Raw | ConvertFrom-Json) } catch { $issues = @() }
        }
    }
    else {
        try {
            $json = & $gh issue list --repo $repo --state open --limit 30 --json number,title,labels 2>$null | Out-String
            if ($LASTEXITCODE -eq 0 -and $json.Trim()) {
                $issues = @($json | ConvertFrom-Json)
            }
        }
        catch { }
    }
    $assigned = @()
    foreach ($issue in @($issues)) {
        if (-not $issue) { continue }
        $numRaw = $issue.number
        if ($numRaw -is [System.Array]) { $numRaw = @($numRaw)[0] }
        try { $num = [int]$numRaw } catch { continue }
        $title = [string]$issue.title
        $labels = @()
        foreach ($lb in @($issue.labels)) {
            if ($lb -is [string]) { $labels += $lb }
            elseif ($lb.name) { $labels += [string]$lb.name }
        }
        $seat = 'dev'
        if ($labels -contains 'mrb') { $seat = 'mrb' }
        $task = "issue #$num $title"
        $r = Assign-BobRepoPairTask -Seat $seat -Task $task -SkipWorkingOnPost
        if ($r.ok) { $assigned += ,[pscustomobject]@{ number = $num; seat = $seat } }
    }
    $s | Add-Member -NotePropertyName lastTicketCheckAt -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
    $s | Add-Member -NotePropertyName lastTicketAssign -NotePropertyValue @($assigned) -Force
    Write-BobRepoPairState $s
    return [pscustomobject]@{ ok = $true; assigned = @($assigned); ticketCount = @($assigned).Count }
}

function Invoke-BobRepoPairBobiverseSay {
    [CmdletBinding()]
    param()
    $s = Read-BobRepoPairState
    if (-not $s) { return [pscustomobject]@{ ok = $true; said = @() } }
    if (-not $s.bobiverseSaid) {
        $s | Add-Member -NotePropertyName bobiverseSaid -NotePropertyValue @() -Force
    }
    $said = @($s.bobiverseSaid)
    $out = @()
    $repo = [string]$s.repo
    $digestPath = Get-BobDigestWebhookLastPostPath
    $digest = Read-JsonFile $digestPath
    foreach ($role in @('dev', 'mrb')) {
        $seat = $null
        if ($s.seats) { $seat = $s.seats.$role }
        if (-not $seat) { continue }
        $lc = [string]$seat.lastComplete
        if (-not $lc) { continue }
        $key = "$role|$lc|$($seat.workingOn)"
        if ($said -contains $key) { continue }
        $line = $null
        if ($lc -match 'dev_complete') {
            $line = "Bob digest: dev complete for $repo ($($seat.workingOn))."
        }
        elseif ($lc -match 'mrb_complete') {
            $line = "Bob digest: MRB complete for $repo ($($seat.workingOn))."
        }
        elseif ($lc -match 'mrb_fail') {
            $line = "Bob digest: MRB FAIL for $repo ($($seat.workingOn))."
        }
        if (-not $line -and $digest -and $digest.working_on) {
            $wo = [string]$digest.working_on
            if ($wo -match 'dev complete') { $line = "Bob digest: dev complete for $repo ($wo)." }
            elseif ($wo -match 'mrb_complete|MRB complete') { $line = "Bob digest: MRB complete for $repo ($wo)." }
        }
        if ($line) {
            Add-BobIrcBobiversePrivmsg -Text $line
            $said += $key
            $out += $line
        }
    }
    $drain = $null
    if ($out.Count -gt 0) {
        try {
            $drain = Invoke-BobIrcDrainOutboxLines -MatchPrefix @('PRIVMSG #bobiverse')
        }
        catch { }
        $s | Add-Member -NotePropertyName bobiverseSaid -NotePropertyValue @($said) -Force
        Write-BobRepoPairState $s
    }
    return [pscustomobject]@{ ok = $true; said = @($out); drained = $(if ($drain) { @($drain.drained) } else { @() }) }
}

function Get-BobRepoPairTicketIntervalSec {
    if ($env:BOB_REPO_PAIR_TICKET_INTERVAL_SEC -and $env:BOB_REPO_PAIR_TICKET_INTERVAL_SEC.Trim()) {
        try { return [int]$env:BOB_REPO_PAIR_TICKET_INTERVAL_SEC } catch { }
    }
    return 7200
}

function Test-BobRepoPairBusinessHours {
    $tzId = 'GMT Standard Time'
    if ($env:BOB_REPO_PAIR_BUSINESS_TZ -and $env:BOB_REPO_PAIR_BUSINESS_TZ.Trim()) {
        $tzId = $env:BOB_REPO_PAIR_BUSINESS_TZ.Trim()
    }
    try { $tz = [TimeZoneInfo]::FindSystemTimeZoneById($tzId) } catch { return $true }
    $local = [TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $tz)
    if ($local.DayOfWeek -in @([DayOfWeek]::Saturday, [DayOfWeek]::Sunday)) { return $false }
    $startH = 9
    $endH = 17
    if ($env:BOB_REPO_PAIR_BUSINESS_START_HOUR) {
        try { $startH = [int]$env:BOB_REPO_PAIR_BUSINESS_START_HOUR } catch { }
    }
    if ($env:BOB_REPO_PAIR_BUSINESS_END_HOUR) {
        try { $endH = [int]$env:BOB_REPO_PAIR_BUSINESS_END_HOUR } catch { }
    }
    return ($local.Hour -ge $startH -and $local.Hour -lt $endH)
}

function Test-BobRepoPairTicketCadenceDue {
    [CmdletBinding()]
    param([switch]$Force)
    if ($Force) { return $true }
    if (-not (Test-BobRepoPairBusinessHours)) { return $false }
    $s = Read-BobRepoPairState
    if (-not $s) { return $false }
    $interval = Get-BobRepoPairTicketIntervalSec
    if (-not $s.lastTicketCheckAt) { return $true }
    try {
        $last = [DateTime]::Parse([string]$s.lastTicketCheckAt, $null, [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
        $age = ([DateTime]::UtcNow - $last).TotalSeconds
        return ($age -ge $interval)
    }
    catch { return $true }
}

function Get-BobRepoPairShopPingIntervalSec {
    if ($env:BOB_REPO_PAIR_SHOP_PING_SEC -and $env:BOB_REPO_PAIR_SHOP_PING_SEC.Trim()) {
        try { return [int]$env:BOB_REPO_PAIR_SHOP_PING_SEC } catch { }
    }
    return 900
}

function Invoke-BobRepoPairShopPing {
    [CmdletBinding()]
    param()
    $s = Read-BobRepoPairState
    if (-not $s -or -not $s.repo) {
        return [pscustomobject]@{ ok = $true; skipped = 'no_pair' }
    }
    $interval = Get-BobRepoPairShopPingIntervalSec
    if ($s.lastShopPingAt) {
        try {
            $last = [DateTime]::Parse([string]$s.lastShopPingAt, $null, [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
            $age = ([DateTime]::UtcNow - $last).TotalSeconds
            if ($age -lt $interval) {
                return [pscustomobject]@{ ok = $true; skipped = 'cadence' }
            }
        }
        catch { }
    }
    $mid = [string]$s.machineId
    if (-not $mid) { $mid = Get-ThisMachineId }
    $chan = Get-BobShopChannelForMachine -MachineId $mid
    if ($chan) {
        Add-BobIrcOutboxChannelLine ("PRIVMSG $chan :Bob shop ping - checking repo-pair worker seats.")
    }
    $intervened = @()
    foreach ($role in @('dev', 'mrb')) {
        $seat = $null
        if ($s.seats) { $seat = $s.seats.$role }
        if (-not $seat) { continue }
        if (-not (Test-BobRepoPairSeatAlive -Seat $seat)) {
            $intervened += $role
            if ($seat.sessionId) {
                Stop-BobWorker -SessionId ([string]$seat.sessionId) | Out-Null
                $seat | Add-Member -NotePropertyName sessionId -NotePropertyValue $null -Force
            }
            Ensure-BobRepoPairSeat -State $s -Role $role -Cwd ([string]$s.cwd) -Repo ([string]$s.repo) | Out-Null
        }
    }
    $s | Add-Member -NotePropertyName lastShopPingAt -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
    Write-BobRepoPairState $s
    return [pscustomobject]@{ ok = $true; intervened = @($intervened) }
}

function Get-BobBobiverseAgentsIdleOverSec {
    [CmdletBinding()]
    param([int]$MinIdleSec = 20)
    $home = Get-BobIrcHome
    if (-not $home) { return @() }
    $peersDir = Join-Path $home 'bob-peers'
    if (-not (Test-Path -LiteralPath $peersDir)) { return @() }
    $now = [DateTime]::UtcNow
    $idle = @()
    foreach ($f in @(Get-ChildItem -LiteralPath $peersDir -Filter '*.json' -ErrorAction SilentlyContinue)) {
        $doc = Read-JsonFile $f.FullName
        if (-not $doc -or -not $doc.id) { continue }
        $seen = $null
        if ($doc.lastSeen) {
            try {
                $seen = [DateTime]::Parse([string]$doc.lastSeen, $null, [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
            }
            catch { continue }
        }
        if (-not $seen) { continue }
        $age = ($now - $seen).TotalSeconds
        if ($age -lt $MinIdleSec) { continue }
        $run = $false
        if ($doc.running -eq $true -or [string]$doc.running -eq '1') { $run = $true }
        if ($run) { continue }
        $idle += ,[pscustomobject]@{ machineId = [string]$doc.id; idleSec = [int]$age }
    }
    return @($idle)
}

function Invoke-BobRepoPairChairIdleAssign {
    [CmdletBinding()]
    param(
        [int]$MinIdleSec = 20
    )
    $idlePeers = @(Get-BobBobiverseAgentsIdleOverSec -MinIdleSec $MinIdleSec)
    $assigned = @()
    $s = Read-BobRepoPairState
    if (-not $s -or -not $s.repo) {
        return [pscustomobject]@{ ok = $true; idlePeers = @($idlePeers); assigned = @() }
    }
    foreach ($role in @('dev', 'mrb')) {
        $seat = $null
        if ($s.seats) { $seat = $s.seats.$role }
        if (-not $seat) { continue }
        $busy = $false
        if ($seat.lastActiveAt) {
            try {
                $last = [DateTime]::Parse([string]$seat.lastActiveAt, $null, [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
                $age = ([DateTime]::UtcNow - $last).TotalSeconds
                if ($age -lt $MinIdleSec) { $busy = $true }
            }
            catch { }
        }
        if ($busy) { continue }
        if ($seat.chairTask -and [string]$seat.chairTask.Trim()) { continue }
        if ($idlePeers.Count -eq 0) { continue }
        $peer = $idlePeers[0]
        $task = "bobiverse idle assign ($($peer.machineId) idle $($peer.idleSec)s): pick up next $role work on $($s.repo)"
        $r = Assign-BobRepoPairTask -Seat $role -Task $task -SkipWorkingOnPost
        if ($r.ok) {
            $assigned += ,[pscustomobject]@{ seat = $role; peer = $peer.machineId; task = $task }
            $idlePeers = @($idlePeers | Select-Object -Skip 1)
        }
    }
    return [pscustomobject]@{ ok = $true; idlePeers = @($idlePeers); assigned = @($assigned) }
}

function Invoke-BobRepoPairMrbSeatHygiene {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][ValidateSet('dev', 'mrb')][string]$Seat,
        [string]$WorkerDir
    )
    if ($Seat -ne 'mrb') { return [pscustomobject]@{ ok = $true; skipped = 'not_mrb' } }
    $dir = $WorkerDir
    if (-not $dir) { return [pscustomobject]@{ ok = $false; error = 'no_worker_dir' } }
    $stampPath = Join-Path $dir 'outbox\mrb-hygiene-last.txt'
    if (Test-Path $stampPath) {
        try {
            $prev = [DateTime]::Parse((Get-Content $stampPath -Raw).Trim(), $null, [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
            if (([DateTime]::UtcNow - $prev).TotalSeconds -lt 900) {
                return [pscustomobject]@{ ok = $true; skipped = 'cadence' }
            }
        }
        catch { }
    }
    $s = Read-BobRepoPairState
    $repo = $(if ($s -and $s.repo) { [string]$s.repo } else { $null })
    if (-not $repo) { return [pscustomobject]@{ ok = $true; skipped = 'no_repo' } }
    $gh = $env:BOB_GH_EXE
    if (-not $gh) { $gh = 'gh' }
    $actions = @()
    if ($env:BOB_FAKE_GH_MODE) {
        $actions += 'fake_hygiene'
    }
    else {
        try {
            $open = & $gh issue list --repo $repo --state open --limit 50 --json number,title 2>$null | Out-String
            if ($LASTEXITCODE -eq 0 -and $open.Trim()) {
                $issues = @($open | ConvertFrom-Json)
                $seen = @{}
                foreach ($issue in $issues) {
                    if (-not $issue) { continue }
                    $title = ([string]$issue.title).Trim().ToLowerInvariant()
                    if (-not $title) { continue }
                    if ($seen.ContainsKey($title)) {
                        $dup = [int]$issue.number
                        & $gh issue close $dup --repo $repo --comment 'MRB seat: duplicate issue closed' 2>$null | Out-Null
                        $actions += "closed_dup_$dup"
                    }
                    else {
                        $seen[$title] = $true
                    }
                }
            }
        }
        catch { }
    }
    [IO.File]::WriteAllText($stampPath, [DateTime]::UtcNow.ToString('o'))
    return [pscustomobject]@{ ok = $true; actions = @($actions) }
}

function Invoke-BobRepoPairChairTick {
    [CmdletBinding()]
    param()
    try { Invoke-BobRepoPairShopPing | Out-Null } catch { }
    $tick = Invoke-BobRepoPairTick
    $idleAssign = Invoke-BobRepoPairChairIdleAssign
    $ticket = [pscustomobject]@{ ok = $true; skipped = 'cadence' }
    if (Test-BobRepoPairTicketCadenceDue) {
        $ticket = Invoke-BobRepoPairOutstandingTickets
    }
    $say = Invoke-BobRepoPairBobiverseSay
    try { Invoke-BobRepoPairChairUsageWebhookIfChanged | Out-Null } catch { }
    return [pscustomobject]@{
        ok         = $true
        tickets    = $ticket
        tick       = $tick
        bobiverse  = $say
        idleAssign = $idleAssign
    }
}

function Get-BobRepoPairBobiverseReport {
    [CmdletBinding()]
    param()
    $s = Read-BobRepoPairState
    if (-not $s) { return @() }
    $lines = New-Object System.Collections.Generic.List[string]
    $repo = [string]$s.repo
    foreach ($role in @('dev', 'mrb')) {
        $seat = $null
        if ($s.seats) { $seat = $s.seats.$role }
        if (-not $seat) { continue }
        $lc = [string]$seat.lastComplete
        if (-not $lc) { continue }
        if ($lc -match 'dev_complete') {
            [void]$lines.Add("Bob digest: dev complete for $repo ($($seat.workingOn)).")
        }
        elseif ($lc -match 'mrb_complete') {
            [void]$lines.Add("Bob digest: MRB complete for $repo ($($seat.workingOn)).")
        }
        elseif ($lc -match 'mrb_fail') {
            [void]$lines.Add("Bob digest: MRB FAIL for $repo ($($seat.workingOn)).")
        }
    }
    return @($lines)
}

function Set-BobShopChannelRepoDescription {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Repo,
        [string]$MachineId
    )
    $mid = $MachineId
    if (-not $mid) { $mid = Get-ThisMachineId }
    $chan = Get-BobShopChannelForMachine -MachineId $mid
    if (-not $chan) {
        return [pscustomobject]@{ ok = $false; error = 'no_machine' }
    }
    $home = Get-BobIrcHome
    if (-not $home) {
        return [pscustomobject]@{ ok = $false; error = 'no_irc_home' }
    }
    New-Item -ItemType Directory -Force -Path $home | Out-Null
    $path = Join-Path $home 'pending-shop-topic.txt'
    $line = ($chan + "`t" + [string]$Repo)
    [IO.File]::WriteAllText($path, $line)
    Sync-BobShopChannelRepoDescriptions | Out-Null
    $s = Read-BobRepoPairState
    if ($s) {
        $s | Add-Member -NotePropertyName channelDescription -NotePropertyValue ([string]$Repo) -Force
        Write-BobRepoPairState $s
    }
    return [pscustomobject]@{ ok = $true; channel = $chan; repo = [string]$Repo; path = $path }
}
