# Shop backup for Jeeves GIT work (Simon 2026-09-24, webhook follow-up).
# Not-yet-accepted rows live on the digest webhook (reportUrl), owned by
# agentic_irc #197. This file does not write that queue or the chair outbox.
# w-* idle > 2 min says !BORED only. Jeeves answers !TASK and marks the
# top row accepted in that step. This worker does not say !ACCEPT.
# Copilot stays off (no Allow switch on Start-BobBuild).

function Get-BobGitChairNicks {
    $nicks = New-Object System.Collections.Generic.List[string]
    function Add-Nick([string]$Name) {
        $t = ([string]$Name).Trim()
        if (-not $t) { return }
        foreach ($have in @($nicks)) {
            if ($have -eq $t) { return }
        }
        $nicks.Add($t) | Out-Null
    }
    Add-Nick 'Jeeves'
    $cfg = $null
    try { $cfg = Get-BobiverseConfig } catch { }
    if ($cfg -and $cfg.chairNick) { Add-Nick ([string]$cfg.chairNick) }
    if ($env:BOB_IRC_CHAIR_NICK -and $env:BOB_IRC_CHAIR_NICK.Trim()) {
        Add-Nick $env:BOB_IRC_CHAIR_NICK.Trim()
    }
    return @($nicks)
}

function ConvertFrom-BobGitTask {
    <#
      Jeeves reply to !BORED. Wire id keeps the # prefix (agentic_irc #197).
      !TASK owner/repo MRB #44
    #>
    param([string]$Body)
    $raw = ([string]$Body).Trim()
    if ($raw -notmatch '^(?i)!TASK\s+(\S+)\s+(PR|MRB)\s+#(\d+)\s*$') { return $null }
    $repo = [string]$Matches[1]
    $task = ([string]$Matches[2]).ToUpperInvariant()
    $num = [string]$Matches[3]
    if ($repo -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$') { return $null }
    return [pscustomobject]@{
        repo   = $repo
        task   = $task
        id     = ('#' + $num)
        number = $num
        source = 'task'
    }
}

function Test-BobGitBoredNak {
    param([string]$Body)
    $raw = ([string]$Body).Trim()
    if ($raw -notmatch '^(?i)NAK !BORED (wait|busy|empty)$') { return $null }
    return ([string]$Matches[1]).ToLowerInvariant()
}

function ConvertFrom-BobGitAnnounce {
    <#
      Allowlist matches agentic_irc #197. ping, push, synchronize, labeled,
      and every other action return null. Id is #n.
    #>
    param([string]$Body)
    $raw = ([string]$Body).Trim()
    if (-not $raw.StartsWith('GIT ')) { return $null }
    $rest = $raw.Substring(4).Trim()
    if (-not $rest) { return $null }
    $parts = @($rest -split '\s+' | Where-Object { $_ })
    if ($parts.Count -lt 2) { return $null }
    $event = ([string]$parts[0]).ToLowerInvariant()
    if ($event -eq 'ping') { return $null }
    $repo = [string]$parts[1]
    if ($repo -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$') { return $null }
    $action = $null
    $id = $null
    $tail = @()
    if ($parts.Count -gt 2) { $tail = @($parts[2..($parts.Count - 1)]) }
    foreach ($tok in $tail) {
        if (-not $action -and $tok -notmatch '^#' -and $tok -ne 'by') {
            $action = ([string]$tok).ToLowerInvariant()
            continue
        }
        if ($tok -match '^#(\d+)$') { $id = '#' + [string]$Matches[1] }
    }
    if (-not $id -or -not $action) { return $null }
    $task = $null
    if ($event -eq 'issues' -and $action -eq 'opened') { $task = 'PR' }
    elseif ($event -eq 'pull_request' -and @('opened', 'ready_for_review') -contains $action) { $task = 'MRB' }
    if (-not $task) { return $null }
    return [pscustomobject]@{
        repo   = $repo
        task   = $task
        id     = $id
        number = $id.TrimStart('#')
        event  = $event
        action = $action
        source = 'git'
    }
}

function Get-BobGitUnacceptedRows {
    param($Doc)
    if (-not $Doc) { return @() }
    $items = $null
    if ($Doc.git_unaccepted) {
        $block = $Doc.git_unaccepted
        if ($block.items) { $items = @($block.items) }
        elseif ($block -is [System.Array]) { $items = @($block) }
    }
    if (-not $items -and $Doc.items) { $items = @($Doc.items) }
    if (-not $items) { return @() }
    $rows = @()
    foreach ($item in $items) {
        if (-not $item) { continue }
        $repo = [string]$item.repo
        $task = ([string]$item.task).ToUpperInvariant()
        $idRaw = [string]$item.id
        if ($idRaw -match '^#(\d+)$') { $id = '#' + $Matches[1]; $num = $Matches[1] }
        elseif ($idRaw -match '^(\d+)$') { $id = '#' + $Matches[1]; $num = $Matches[1] }
        else { continue }
        if ($repo -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$') { continue }
        if (@('PR', 'MRB') -notcontains $task) { continue }
        $seq = 0
        if ($null -ne $item.seq -and [string]$item.seq -ne '') {
            try { $seq = [int]$item.seq } catch { $seq = 0 }
        }
        $rows += [pscustomobject]@{
            repo   = $repo
            task   = $task
            id     = $id
            number = $num
            seq    = $seq
            ts     = $(if ($item.ts) { [string]$item.ts } else { $null })
            event  = $(if ($item.event) { [string]$item.event } else { $null })
            action = $(if ($item.action) { [string]$item.action } else { $null })
        }
    }
    return @($rows | Sort-Object seq, ts, repo, task, id)
}

function Get-BobGitUnaccepted {
    <#
      Read-only view of not-yet-accepted GIT rows on the digest document.
      Field git_unaccepted.items matches agentic_irc git-unaccepted.json.
      Never writes the digest or a local queue file.
    #>
    param(
        $Digest,
        [string]$JsonPath
    )
    $doc = $Digest
    if (-not $doc -and $JsonPath) {
        if (-not (Test-Path -LiteralPath $JsonPath)) { return @() }
        try { $doc = Read-JsonFile $JsonPath } catch { return @() }
    }
    if (-not $doc) {
        try { $doc = Read-BobReportDigest } catch { $doc = $null }
    }
    return @(Get-BobGitUnacceptedRows $doc)
}

function Add-BobWorkerShopOutboxLine {
    param(
        [Parameter(Mandatory)][string]$WorkerHome,
        [Parameter(Mandatory)][string]$Line
    )
    $text = $Line.Trim()
    if (-not $text) { return }
    if (-not (Test-Path -LiteralPath $WorkerHome)) {
        New-Item -ItemType Directory -Force -Path $WorkerHome | Out-Null
    }
    $outbox = Join-Path $WorkerHome 'outbox.txt'
    # boredSent is the once-per-stretch guard. A later idle stretch must
    # append !BORED again even when the previous line is still the tail.
    Add-Content -LiteralPath $outbox -Value $text -Encoding utf8
}

function Get-BobWorkerBoredStatePath {
    param([Parameter(Mandatory)][string]$WorkerHome)
    Join-Path $WorkerHome 'bored-state.json'
}

function Read-BobWorkerBoredState {
    param([Parameter(Mandatory)][string]$WorkerHome)
    $p = Get-BobWorkerBoredStatePath $WorkerHome
    $idleSince = $null
    $boredSent = $false
    $boredAtBytes = 0
    if (Test-Path -LiteralPath $p) {
        try {
            $j = Read-JsonFile $p
            if ($j) {
                if ($j.idleSince) {
                    try {
                        $idleSince = [datetime]::Parse([string]$j.idleSince, $null, [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
                    }
                    catch { $idleSince = $null }
                }
                if ($j.boredSent) { $boredSent = [bool]$j.boredSent }
                if ($null -ne $j.boredAtBytes -and [string]$j.boredAtBytes -ne '') {
                    try { $boredAtBytes = [int]$j.boredAtBytes } catch { $boredAtBytes = 0 }
                }
            }
        }
        catch { }
    }
    return [pscustomobject]@{
        idleSince    = $idleSince
        boredSent    = $boredSent
        boredAtBytes = $boredAtBytes
    }
}

function Write-BobWorkerBoredState {
    param(
        [Parameter(Mandatory)][string]$WorkerHome,
        [datetime]$IdleSince,
        [bool]$BoredSent,
        [int]$BoredAtBytes = 0
    )
    $doc = [ordered]@{
        boredSent    = [bool]$BoredSent
        boredAtBytes = [int]$BoredAtBytes
    }
    if ($IdleSince -and $IdleSince -ne [datetime]::MinValue) {
        $doc.idleSince = $IdleSince.ToUniversalTime().ToString('o')
    }
    else {
        $doc.idleSince = $null
    }
    Write-JsonFile (Get-BobWorkerBoredStatePath $WorkerHome) ([pscustomobject]$doc)
}

function Get-BobWorkerIrcLogSnapshot {
    param([Parameter(Mandatory)][string]$WorkerHome)
    $logPath = Join-Path $WorkerHome 'irc.log'
    if (-not (Test-Path -LiteralPath $logPath)) {
        return [pscustomobject]@{ text = ''; length = 0 }
    }
    $raw = [IO.File]::ReadAllBytes($logPath)
    return [pscustomobject]@{
        text   = [Text.Encoding]::UTF8.GetString($raw)
        length = $raw.Length
    }
}

function Get-BobShopPrivmsgLines {
    param([string]$Text)
    $rows = @()
    if (-not $Text) { return $rows }
    foreach ($line in @($Text -split "`n")) {
        $t = ([string]$line).Trim()
        if (-not $t) { continue }
        if ($t -match '^:(?<nick>[^!\s]+)![^\s]*\s+PRIVMSG\s+(?<target>\S+)\s+:(?<body>.*)$') {
            $rows += [pscustomobject]@{
                nick   = [string]$Matches['nick']
                target = [string]$Matches['target']
                body   = ([string]$Matches['body']).Trim()
            }
        }
    }
    return $rows
}

function Test-BobGitChairNick {
    param([string]$Nick, [string[]]$ChairNicks)
    if (-not $Nick) { return $false }
    foreach ($c in @($ChairNicks)) {
        if ($c -and ($c.ToLowerInvariant() -eq $Nick.ToLowerInvariant())) { return $true }
    }
    return $false
}

function Test-BobShopOfferTarget {
    param([string]$Target, [string]$ShopChannel, [string]$WorkerNick)
    $tg = ([string]$Target).Trim().ToLowerInvariant()
    if (-not $tg) { return $false }
    if ($tg -eq '#bobiverse') { return $false }
    if ($ShopChannel -and $tg -eq $ShopChannel.Trim().ToLowerInvariant()) { return $true }
    if ($WorkerNick -and $tg -eq $WorkerNick.Trim().ToLowerInvariant()) { return $true }
    return $false
}

function Get-BobGitAcceptClaimPath {
    param([Parameter(Mandatory)][string]$WorkerHome)
    $parent = Split-Path -Parent $WorkerHome
    if (-not $parent) { return $null }
    Join-Path $parent '_git-accept-claims.json'
}

function Get-BobGitAcceptClaimKey {
    param([string]$Repo, [string]$Task, [string]$Id)
    return ($Repo + '|' + $Task.ToUpperInvariant() + '|' + $Id)
}

function Test-BobGitAcceptLocalClaim {
    param(
        [Parameter(Mandatory)][string]$WorkerHome,
        [string]$Repo,
        [string]$Task,
        [string]$Id
    )
    $p = Get-BobGitAcceptClaimPath $WorkerHome
    if (-not $p -or -not (Test-Path -LiteralPath $p)) { return $false }
    try {
        $j = Read-JsonFile $p
    }
    catch { return $false }
    if (-not $j) { return $false }
    $key = Get-BobGitAcceptClaimKey -Repo $Repo -Task $Task -Id $Id
    foreach ($prop in @($j.PSObject.Properties)) {
        if ($prop.Name -eq $key) { return $true }
    }
    return $false
}

function Set-BobGitAcceptLocalClaim {
    param(
        [Parameter(Mandatory)][string]$WorkerHome,
        [string]$Repo,
        [string]$Task,
        [string]$Id,
        [string]$WorkerNick
    )
    $p = Get-BobGitAcceptClaimPath $WorkerHome
    if (-not $p) { return }
    $map = [ordered]@{}
    if (Test-Path -LiteralPath $p) {
        try {
            $j = Read-JsonFile $p
            if ($j) {
                foreach ($prop in @($j.PSObject.Properties)) { $map[$prop.Name] = [string]$prop.Value }
            }
        }
        catch { }
    }
    $key = Get-BobGitAcceptClaimKey -Repo $Repo -Task $Task -Id $Id
    $map[$key] = $(if ($WorkerNick) { $WorkerNick } else { 'w' })
    $dir = Split-Path -Parent $p
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    Write-JsonFile $p ([pscustomobject]$map)
}

function Remove-BobGitAcceptLocalClaim {
    param(
        [Parameter(Mandatory)][string]$WorkerHome,
        [string]$Repo,
        [string]$Task,
        [string]$Id
    )
    $p = Get-BobGitAcceptClaimPath $WorkerHome
    if (-not $p -or -not (Test-Path -LiteralPath $p)) { return }
    $key = Get-BobGitAcceptClaimKey -Repo $Repo -Task $Task -Id $Id
    $map = [ordered]@{}
    try {
        $j = Read-JsonFile $p
        if ($j) {
            foreach ($prop in @($j.PSObject.Properties)) {
                if ($prop.Name -ne $key) { $map[$prop.Name] = [string]$prop.Value }
            }
        }
    }
    catch { return }
    Write-JsonFile $p ([pscustomobject]$map)
}

function Get-BobGitAcceptBusyPath {
    param([Parameter(Mandatory)][string]$WorkerHome)
    Join-Path $WorkerHome 'git-accept-busy.json'
}

function Test-BobGitAcceptWorkerBusy {
    <#
      True while the accepted fleet job is still inbox or running.
      A missing job drops the local busy stamp (activity clear). Does not touch the chair queue.
    #>
    param([Parameter(Mandatory)][string]$WorkerHome)
    $p = Get-BobGitAcceptBusyPath $WorkerHome
    if (-not (Test-Path -LiteralPath $p)) { return $false }
    $jobId = $null
    try {
        $j = Read-JsonFile $p
        if ($j -and $j.jobId) { $jobId = [string]$j.jobId }
    }
    catch { return $true }
    if (-not $jobId) {
        Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue
        return $false
    }
    $live = $false
    try {
        foreach ($row in @(Get-BobBuilds)) {
            if (-not $row) { continue }
            if ([string]$row.id -ne $jobId) { continue }
            $lane = [string]$row.lane
            if ($lane -eq 'inbox' -or $lane -eq 'running') { $live = $true; break }
        }
    }
    catch { return $true }
    if ($live) { return $true }
    Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue
    return $false
}

function Write-BobGitAcceptBusy {
    param(
        [Parameter(Mandatory)][string]$WorkerHome,
        [Parameter(Mandatory)][string]$JobId,
        $Claim
    )
    $doc = [ordered]@{
        jobId = $JobId
        repo  = [string]$Claim.repo
        task  = [string]$Claim.task
        id    = [string]$Claim.id
        at    = [datetime]::UtcNow.ToString('o')
    }
    Write-JsonFile (Get-BobGitAcceptBusyPath $WorkerHome) ([pscustomobject]$doc)
}

function Start-BobGitAcceptWork {
    <#
      Enqueue on this machine via Start-BobBuild. Copilot stays off.
      Cursor Models then grok-build (Get-BobFuelOrder inside the picker).
      The inbox job is the activity row; Write-BobIrcStatus drops it when the job leaves inbox/running.
    #>
    param(
        [Parameter(Mandatory)]$Claim,
        [string]$MachineId,
        [string]$WorkerHome
    )
    if (-not $MachineId) {
        return [pscustomobject]@{ ok = $false; wait = $true; jobId = $null; reason = 'machine_required' }
    }
    $task = ([string]$Claim.task).ToUpperInvariant()
    $kind = 'build'
    if ($task -eq 'MRB') { $kind = 'mrb' }
    $repo = [string]$Claim.repo
    $num = [string]$Claim.number
    if (-not $num) { $num = ([string]$Claim.id).TrimStart('#') }
    $url = 'https://github.com/' + $repo
    $goal = "Jeeves !TASK $repo $task #$num. Work item $url . Finish with the existing git job. Do not use Copilot. Do not use Other Models. Do not merge."
    if ($task -eq 'MRB') {
        $goal = "Jeeves !TASK $repo MRB #$num. Hostile MRB of $url/pull/$num . Follow skill bob-hostile-mrb. Do not use Copilot. Do not use Other Models."
    }
    $buildArgs = @{
        Task    = 'git'
        Machine = $MachineId
        Kind    = $kind
        Repo    = $url
        Goal    = $goal
        From    = 'git-accept'
    }
    if ($task -eq 'MRB') { $buildArgs['PrUrl'] = ($url + '/pull/' + $num) }
    return (Start-BobBuild @buildArgs)
}

function Get-BobGitWorkAgentLabel {
    param([string]$Fuel)
    switch (([string]$Fuel).ToLowerInvariant()) {
        'cursor-models' { return 'Cursor Models' }
        'grok-build' { return 'grok.exe' }
        'grok-bot' { return 'Grok Bot' }
        default { return [string]$Fuel }
    }
}

function Send-BobGitWorkActivity {
    <#
      Digest webhook merge. working_on carries agent and model.
      clear sends an empty working_on. Does not replace the jobs list.
    #>
    param(
        [Parameter(Mandatory)][ValidateSet('start', 'clear')][string]$Phase,
        [string]$MachineId,
        $Claim,
        $Start
    )
    if (-not $MachineId) { return $null }
    $working = ''
    $model = ''
    $fuel = ''
    $kind = ''
    $repo = ''
    if ($Phase -eq 'start' -and $Claim) {
        $fuel = [string]$Start.fuel
        $model = [string]$Start.model
        $agent = Get-BobGitWorkAgentLabel $fuel
        $id = [string]$Claim.id
        if ($id -notmatch '^#') { $id = '#' + $id.TrimStart('#') }
        $working = (@($agent, $model, [string]$Claim.task, ([string]$Claim.repo + $id)) | Where-Object { $_ }) -join ' '
        $repo = [string]$Claim.repo
        if ([string]$Claim.task -eq 'MRB') { $kind = 'mrb' } else { $kind = 'build' }
    }
    $payload = [ordered]@{
        op         = 'merge'
        machine    = $MachineId
        online     = $true
        status     = 'I am online'
        working_on = $working
    }
    if ($Phase -eq 'start') {
        if ($model) { $payload.model = $model }
        if ($fuel) { $payload.fuel = $fuel }
        if ($kind) { $payload.kind = $kind }
        if ($repo) { $payload.repo = $repo }
    }
    return (Invoke-BobDigestWebhookMergePost -Payload ([pscustomobject]$payload))
}

function Invoke-BobWorkerShopTick {
    <#
      One w-* home. Idle >= BoredAfterSeconds (default 120) appends
      PRIVMSG <shop> :!BORED once. The worker never appends !ACCEPT.
      After that byte offset, a chair !TASK on the shop starts work.
      NAK !BORED resets the idle clock. GIT lines are not claims.
    #>
    param(
        [Parameter(Mandatory)][string]$WorkerHome,
        [Parameter(Mandatory)][string]$ShopChannel,
        [bool]$IsBusy = $false,
        [datetime]$Now = ([datetime]::UtcNow),
        [string[]]$ChairNicks,
        [string]$WorkerNick,
        [string]$MachineId,
        [scriptblock]$StartWork,
        [int]$BoredAfterSeconds = 120,
        [switch]$SkipActivity
    )
    if (-not $ChairNicks -or @($ChairNicks).Count -eq 0) { $ChairNicks = @(Get-BobGitChairNicks) }
    $nowUtc = $Now.ToUniversalTime()
    $result = [pscustomobject]@{
        bored   = $false
        started = $false
        nak     = $null
        claim   = $null
        start   = $null
    }
    if ($IsBusy) {
        Write-BobWorkerBoredState -WorkerHome $WorkerHome -BoredSent $false -BoredAtBytes 0
        return $result
    }
    $state = Read-BobWorkerBoredState $WorkerHome
    if (-not $state.idleSince) {
        Write-BobWorkerBoredState -WorkerHome $WorkerHome -IdleSince $nowUtc -BoredSent $false -BoredAtBytes 0
        return $result
    }
    $snap = Get-BobWorkerIrcLogSnapshot $WorkerHome
    if (-not $state.boredSent) {
        $elapsed = ($nowUtc - $state.idleSince.ToUniversalTime()).TotalSeconds
        if ($elapsed -lt $BoredAfterSeconds) { return $result }
        $line = 'PRIVMSG ' + $ShopChannel.Trim() + ' :!BORED'
        Add-BobWorkerShopOutboxLine -WorkerHome $WorkerHome -Line $line
        Write-BobWorkerBoredState -WorkerHome $WorkerHome -IdleSince $state.idleSince -BoredSent $true -BoredAtBytes $snap.length
        $result.bored = $true
        return $result
    }
    $suffix = ''
    if ($state.boredAtBytes -le 0) { $suffix = [string]$snap.text }
    elseif ($state.boredAtBytes -lt $snap.length) {
        $raw = [IO.File]::ReadAllBytes((Join-Path $WorkerHome 'irc.log'))
        $suffix = [Text.Encoding]::UTF8.GetString($raw, $state.boredAtBytes, ($raw.Length - $state.boredAtBytes))
    }
    $nak = $null
    $claim = $null
    foreach ($row in @(Get-BobShopPrivmsgLines $suffix)) {
        if (-not (Test-BobGitChairNick -Nick $row.nick -ChairNicks $ChairNicks)) { continue }
        if (-not (Test-BobShopOfferTarget -Target $row.target -ShopChannel $ShopChannel -WorkerNick $WorkerNick)) { continue }
        $why = Test-BobGitBoredNak $row.body
        if ($why) { $nak = $why; continue }
        $parsed = ConvertFrom-BobGitTask $row.body
        if ($parsed) { $claim = $parsed }
    }
    if ($nak -and -not $claim) {
        Write-BobWorkerBoredState -WorkerHome $WorkerHome -IdleSince $nowUtc -BoredSent $false -BoredAtBytes $snap.length
        $result.nak = $nak
        return $result
    }
    if (-not $claim) { return $result }
    if (Test-BobGitAcceptLocalClaim -WorkerHome $WorkerHome -Repo $claim.repo -Task $claim.task -Id $claim.id) {
        Write-BobWorkerBoredState -WorkerHome $WorkerHome -IdleSince $nowUtc -BoredSent $false -BoredAtBytes $snap.length
        return $result
    }
    Set-BobGitAcceptLocalClaim -WorkerHome $WorkerHome -Repo $claim.repo -Task $claim.task -Id $claim.id -WorkerNick $WorkerNick
    $started = $null
    if ($StartWork) {
        $started = & $StartWork $claim
    }
    else {
        $started = Start-BobGitAcceptWork -Claim $claim -MachineId $MachineId -WorkerHome $WorkerHome
    }
    $result.start = $started
    $result.claim = $claim
    $ok = $false
    if ($started -and $started.ok -and -not $started.wait) { $ok = $true }
    if (-not $ok) {
        Remove-BobGitAcceptLocalClaim -WorkerHome $WorkerHome -Repo $claim.repo -Task $claim.task -Id $claim.id
        Write-BobWorkerBoredState -WorkerHome $WorkerHome -IdleSince $nowUtc -BoredSent $false -BoredAtBytes $snap.length
        return $result
    }
    if ($started.jobId) {
        Write-BobGitAcceptBusy -WorkerHome $WorkerHome -JobId ([string]$started.jobId) -Claim $claim
    }
    if (-not $SkipActivity) {
        try {
            Send-BobGitWorkActivity -Phase start -MachineId $MachineId -Claim $claim -Start $started | Out-Null
        }
        catch { }
        try { Write-BobIrcStatus | Out-Null } catch { }
    }
    Write-BobWorkerBoredState -WorkerHome $WorkerHome -BoredSent $false -BoredAtBytes $snap.length
    $result.started = $true
    return $result
}

function Import-BobWorkerGitShop {
    <#
      Watch-Bobiverse calls this. Local w-* homes only. Read-only toward the chair queue.
    #>
    param(
        [string]$MachineId,
        [datetime]$Now = ([datetime]::UtcNow),
        [scriptblock]$StartWork,
        [int]$BoredAfterSeconds = 120,
        [switch]$SkipActivity
    )
    if (-not $MachineId) {
        try { $MachineId = Get-ThisMachineId } catch { }
    }
    if (-not $MachineId) { return @() }
    $ircHome = $null
    try { $ircHome = Get-BobIrcHome } catch { }
    if (-not $ircHome) { return @() }
    $root = Join-Path $ircHome (Join-Path 'workers' $MachineId)
    if (-not (Test-Path -LiteralPath $root)) { return @() }
    $shop = $null
    try { $shop = Get-BobIrcShopChannel -MachineId $MachineId } catch { }
    if (-not $shop) { return @() }
    $chairs = @(Get-BobGitChairNicks)
    $done = @()
    foreach ($dir in @(Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue)) {
        if ($dir.Name -notmatch '^\d+$') { continue }
        $pid = [int]$dir.Name
        if ($pid -le 0) { continue }
        $nick = $null
        try { $nick = Get-BobWorkerIrcNick -MachineId $MachineId -WorkerPid $pid } catch { $nick = $null }
        $busyPath = Get-BobGitAcceptBusyPath $dir.FullName
        $busyDoc = $null
        if (Test-Path -LiteralPath $busyPath) {
            try { $busyDoc = Read-JsonFile $busyPath } catch { }
        }
        $busy = Test-BobGitAcceptWorkerBusy -WorkerHome $dir.FullName
        if ($busyDoc -and -not $busy -and -not $SkipActivity) {
            try {
                Send-BobGitWorkActivity -Phase clear -MachineId $MachineId -Claim $busyDoc | Out-Null
            }
            catch { }
        }
        try {
            $tick = Invoke-BobWorkerShopTick -WorkerHome $dir.FullName -ShopChannel $shop -IsBusy:$busy -Now $Now `
                -ChairNicks $chairs -WorkerNick $nick -MachineId $MachineId -StartWork $StartWork `
                -BoredAfterSeconds $BoredAfterSeconds -SkipActivity:$SkipActivity
            if ($tick -and ($tick.bored -or $tick.started)) { $done += $tick }
        }
        catch { }
    }
    return $done
}
