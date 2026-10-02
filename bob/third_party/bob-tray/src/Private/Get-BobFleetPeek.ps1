function Invoke-BobTimed {
    param(
        [Parameter(Mandatory)][scriptblock]$Action,
        [object[]]$ArgumentList = @(),
        [int]$TimeoutMs = 1500
    )
    $ms = [Math]::Max(50, [int]$TimeoutMs)
    $run = [powershell]::Create()
    try {
        [void]$run.AddScript($Action.ToString())
        foreach ($a in @($ArgumentList)) {
            [void]$run.AddArgument($a)
        }
        $h = $run.BeginInvoke()
        if (-not $h.AsyncWaitHandle.WaitOne($ms)) {
            try { $run.Stop() } catch { }
            # Timed-out Dns.GetHostAddresses / UNC ignores Stop(); Dispose would
            # wait it out and freeze the idle tray card. Leak this instance.
            $run = $null
            return [pscustomobject]@{ ok = $false; timedOut = $true; value = $null; error = 'timeout' }
        }
        $val = $run.EndInvoke($h)
        $errs = @($run.Streams.Error)
        if ($errs.Count -gt 0) {
            return [pscustomobject]@{ ok = $false; timedOut = $false; value = $null; error = [string]$errs[0] }
        }
        $one = $null
        if ($null -eq $val) { $one = $null }
        elseif ($val -is [System.Collections.IList] -and $val.Count -eq 1) { $one = $val[0] }
        elseif ($val -is [System.Collections.IList] -and $val.Count -eq 0) { $one = @() }
        else { $one = $val }
        return [pscustomobject]@{ ok = $true; timedOut = $false; value = $one; error = $null }
    }
    catch {
        return [pscustomobject]@{ ok = $false; timedOut = $false; value = $null; error = $_.Exception.Message }
    }
    finally {
        if ($run) { $run.Dispose() }
    }
}

function ConvertTo-BobUncPath {
    param([string]$Hostname, [string]$LocalPath)
    if (-not $Hostname -or -not $LocalPath) { return $null }
    $p = [string]$LocalPath.Trim()
    if ($p -match '^\\\\') { return $p }
    if ($p -match '^([A-Za-z]):\\(.*)$') {
        return ('\\{0}\{1}$\{2}' -f $Hostname, $Matches[1], $Matches[2])
    }
    if ($p -match '^([A-Za-z]):\\?$') {
        return ('\\{0}\{1}$\' -f $Hostname, $Matches[1])
    }
    return $null
}

function Test-BobPathIsUnc {
    param([string]$Path)
    if (-not $Path) { return $false }
    return ([string]$Path -match '^\\\\')
}

function Get-BobPeekIoTimeoutMs {
    param([string]$Path, [int]$TimeoutMs)
    if (Test-BobPathIsUnc $Path) { return [Math]::Max(50, [int]$TimeoutMs) }
    return 0
}

function Test-BobHostnameResolves {
    param([string]$Hostname, [int]$TimeoutMs = 400)
    if (-not $Hostname) { return $false }
    if ($Hostname -eq $env:COMPUTERNAME) { return $true }
    # Bare Dns.GetHostAddresses on a missing LAN host can block 15-30s and freeze the tray.
    $r = Invoke-BobTimed -TimeoutMs $TimeoutMs -ArgumentList @($Hostname) -Action {
        param($Name)
        [void][Net.Dns]::GetHostAddresses($Name)
        return $true
    }
    return [bool]($r.ok -and $r.value)
}

function Test-BobLoadBundledRegistry {
    $flag = [string]$env:BOB_FLEET_BUNDLED
    if ($flag -eq '0') { return $false }
    if ($flag -eq '1') { return $true }
    try {
        $root = [IO.Path]::GetFullPath((Get-BridgeRoot))
        $real = [IO.Path]::GetFullPath((Join-Path $env:USERPROFILE '.grok\bob-bridge'))
        return ($root -eq $real)
    }
    catch { return $false }
}

function Get-BobBundledFleetRegistryPath {
    Join-Path (Get-ModuleRoot) 'config\fleet-registry.json'
}

function New-BobRegistryMachine {
    param($M, [string]$Source)
    if (-not $M) { return $null }
    $id = [string]$M.id
    if (-not $id) { return $null }
    $id = $id.Trim().ToLowerInvariant()
    $peek = $null
    if ($M.peekRoot) { $peek = [string]$M.peekRoot }
    $home = $null
    if ($M.bridgeHome) { $home = [string]$M.bridgeHome }
    $hostName = $null
    if ($M.hostname) { $hostName = [string]$M.hostname }
    $seen = $null
    if ($M.lastSeen) { $seen = [string]$M.lastSeen }
    return [pscustomobject]@{
        id         = $id
        hostname   = $hostName
        bridgeHome = $home
        peekRoot   = $peek
        lastSeen   = $seen
        source     = $Source
    }
}

function Merge-BobRegistryMachine {
    param($ById, $M, [string]$Source)
    $row = New-BobRegistryMachine -M $M -Source $Source
    if (-not $row) { return }
    if (-not $ById.ContainsKey($row.id)) {
        $ById[$row.id] = $row
        return
    }
    $cur = $ById[$row.id]
    foreach ($prop in @('hostname', 'bridgeHome', 'peekRoot', 'lastSeen')) {
        $v = [string]$cur.$prop
        $n = [string]$row.$prop
        if ($n -and $n.Trim()) {
            $cur | Add-Member -NotePropertyName $prop -NotePropertyValue $n -Force
        }
        elseif (-not $v) {
            $cur | Add-Member -NotePropertyName $prop -NotePropertyValue $n -Force
        }
    }
    if ($Source) {
        $cur | Add-Member -NotePropertyName source -NotePropertyValue $Source -Force
    }
}

function Merge-BobRegistryDoc {
    param($ById, $Doc, [string]$Source, [ref]$StaleAfterSec, [ref]$PeekTimeoutMs, [ref]$ShareRoot, [ref]$Transport)
    if (-not $Doc) { return }
    if ($Doc.staleAfterSec) {
        try { $StaleAfterSec.Value = [int]$Doc.staleAfterSec } catch { }
    }
    if ($Doc.peekTimeoutMs) {
        try { $PeekTimeoutMs.Value = [int]$Doc.peekTimeoutMs } catch { }
    }
    if ($Doc.shareRoot -and [string]$Doc.shareRoot.Trim()) {
        $ShareRoot.Value = [string]$Doc.shareRoot.Trim()
    }
    if ($Doc.transport -and [string]$Doc.transport.Trim()) {
        $Transport.Value = [string]$Doc.transport.Trim()
    }
    foreach ($m in @($Doc.machines)) {
        Merge-BobRegistryMachine -ById $ById -M $m -Source $Source
    }
}

function Get-BobFleetRegistry {
    [CmdletBinding()]
    param()
    $byId = @{}
    $staleAfterSec = 900
    $peekTimeoutMs = 1500
    $shareRoot = $null
    $transport = 'filesystem-readonly'

    if (Test-BobLoadBundledRegistry) {
        $bundled = Get-BobBundledFleetRegistryPath
        if (Test-Path $bundled) {
            Merge-BobRegistryDoc -ById $byId -Doc (Read-JsonFile $bundled) -Source 'bundled' `
                -StaleAfterSec ([ref]$staleAfterSec) -PeekTimeoutMs ([ref]$peekTimeoutMs) `
                -ShareRoot ([ref]$shareRoot) -Transport ([ref]$transport)
        }
    }

    try {
        $localReg = Join-Path (Initialize-FleetRoot) 'registry.json'
        if (Test-Path $localReg) {
            Merge-BobRegistryDoc -ById $byId -Doc (Read-JsonFile $localReg) -Source 'local-registry' `
                -StaleAfterSec ([ref]$staleAfterSec) -PeekTimeoutMs ([ref]$peekTimeoutMs) `
                -ShareRoot ([ref]$shareRoot) -Transport ([ref]$transport)
        }
    }
    catch { }

    $envReg = [string]$env:BOB_FLEET_REGISTRY
    if ($envReg -and $envReg.Trim() -and (Test-Path $envReg.Trim())) {
        Merge-BobRegistryDoc -ById $byId -Doc (Read-JsonFile $envReg.Trim()) -Source 'env' `
            -StaleAfterSec ([ref]$staleAfterSec) -PeekTimeoutMs ([ref]$peekTimeoutMs) `
            -ShareRoot ([ref]$shareRoot) -Transport ([ref]$transport)
    }

    $envShare = [string]$env:BOB_FLEET_SHARE
    if ($envShare -and $envShare.Trim()) { $shareRoot = $envShare.Trim() }

    try {
        foreach ($m in @(Get-BobMachines -ErrorAction SilentlyContinue)) {
            Merge-BobRegistryMachine -ById $byId -M $m -Source 'fleet-machines'
        }
    }
    catch { }

    try {
        $self = Read-JsonFile (Join-Path (Get-BridgeRoot) 'machine.json')
        if ($self) { Merge-BobRegistryMachine -ById $byId -M $self -Source 'machine.json' }
    }
    catch { }

    $thisId = $null
    try { $thisId = Get-ThisMachineId } catch { }
    if ($thisId -and -not $byId.ContainsKey($thisId)) {
        Merge-BobRegistryMachine -ById $byId -M ([pscustomobject]@{
                id         = $thisId
                hostname   = $env:COMPUTERNAME
                bridgeHome = (Get-BridgeRoot)
            }) -Source 'self'
    }

    $rows = @($byId.Values | Sort-Object id)
    return [pscustomobject]@{
        transport      = $transport
        docs           = 'docs/bob-fleet-peer-peek.md'
        staleAfterSec  = [int]$staleAfterSec
        peekTimeoutMs  = [int]$peekTimeoutMs
        shareRoot      = $shareRoot
        machines       = $rows
    }
}

function Write-BobFleetRegistrySelf {
    $id = Get-ThisMachineId
    if (-not $id) { return }
    $path = Join-Path (Initialize-FleetRoot) 'registry.json'
    $doc = Read-JsonFile $path
    if (-not $doc) {
        $doc = [pscustomobject]@{
            transport     = 'filesystem-readonly'
            staleAfterSec = 900
            peekTimeoutMs = 1500
            machines      = @()
        }
    }
    $rec = [pscustomobject]@{
        id         = $id
        hostname   = $env:COMPUTERNAME
        bridgeHome = (Get-BridgeRoot)
        lastSeen   = [DateTime]::UtcNow.ToString('o')
    }
    $out = @()
    $found = $false
    foreach ($m in @($doc.machines)) {
        $mid = [string]$m.id
        if ($mid -and $mid.ToLowerInvariant() -eq $id) {
            if ($m.peekRoot) {
                $rec | Add-Member -NotePropertyName peekRoot -NotePropertyValue ([string]$m.peekRoot) -Force
            }
            $out += $rec
            $found = $true
        }
        else {
            $out += $m
        }
    }
    if (-not $found) { $out += $rec }
    $doc | Add-Member -NotePropertyName machines -NotePropertyValue @($out) -Force
    Write-JsonFile $path $doc
}

function Write-BobFleetMachineStubs {
    $reg = Get-BobFleetRegistry
    $dir = Join-Path (Initialize-FleetRoot) 'machines'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    foreach ($m in @($reg.machines)) {
        $mid = [string]$m.id
        if (-not $mid) { continue }
        $p = Join-Path $dir ($mid + '.json')
        if (Test-Path $p) { continue }
        Write-JsonFile $p ([pscustomobject]@{
                id       = $mid
                hostname = $m.hostname
                lastSeen = $m.lastSeen
            })
    }
}

function Get-BobJobRepoStamp {
    param($Job)
    if (Get-Command Get-BobTrayRepoLabel -ErrorAction SilentlyContinue) {
        try {
            $label = Get-BobTrayRepoLabel -Job $Job
            if ($label -and $label -ne '?') { return $label }
        }
        catch { }
    }
    if ($Job -and $Job.repo) {
        $r = [string]$Job.repo
        if ($r -and $r.Trim() -and $r.Trim() -ne '?' -and -not (Test-BobTrayLooksLikeSha $r)) {
            return $r.Trim()
        }
    }
    $cwd = $null
    if ($Job) { $cwd = [string]$Job.cwd }
    if (Get-Command Get-GitHubSlugFromCwd -ErrorAction SilentlyContinue) {
        try {
            $slug = Get-GitHubSlugFromCwd $cwd
            if ($slug -and $slug -ne '?') { return $slug }
        }
        catch { }
    }
    if ($cwd) {
        try {
            $leaf = Split-Path $cwd -Leaf
            if ($leaf -and -not (Test-BobTrayLooksLikeSha $leaf)) {
                if ($leaf -match '^agentic_build') { return 'SimonBarnett/agentic_build' }
                if ($leaf -match '^agentic_irc') { return 'SimonBarnett/agentic_irc' }
                return $leaf
            }
        }
        catch { }
    }
    return $null
}

function ConvertTo-BobPeekJob {
    param($Job, [string]$MachineId, [string]$Lane, [switch]$StampRepo)
    if (-not $Job) { return $null }
    $st = $null
    if ($Job.state) { $st = [string]$Job.state }
    if (-not $st) {
        if ($Lane -eq 'inbox') { $st = 'queued' } else { $st = 'running' }
    }
    $mac = $MachineId
    if ($Job.machine) { $mac = [string]$Job.machine }
    $repo = $null
    if ($StampRepo) { $repo = Get-BobJobRepoStamp $Job }
    elseif ($Job.repo) { $repo = [string]$Job.repo }
    return [pscustomobject]@{
        id        = [string]$Job.id
        machine   = $mac
        cwd       = [string]$Job.cwd
        repo      = $repo
        claimedAt = $Job.claimedAt
        createdAt = $Job.createdAt
        sessionId = $(if ($Job.sessionId) { [string]$Job.sessionId } else { $null })
        state     = $st
        lane      = $Lane
    }
}

function Normalize-BobPeerLaneJobsResult {
    param($LaneJobs)
    # Get-BobPeerLaneJobs returns $null on I/O failure; @($null).Count is 1 in PowerShell.
    if ($null -eq $LaneJobs) { return @() }
    return @($LaneJobs)
}

function Test-BobFleetJobProcessLive {
    param(
        $Job,
        [int]$OrphanSec = 600
    )
    if (-not $Job) { return $false }
    $sid = $null
    if ($Job.sessionId) { $sid = [string]$Job.sessionId }
    elseif ($Job.id) { $sid = [string]$Job.id }
    if ($sid) {
        try {
            if (Test-BobJobProcess -SessionId $sid) { return $true }
        }
        catch { }
        return $false
    }
    $when = $null
    if ($Job.claimedAt) { $when = [string]$Job.claimedAt }
    elseif ($Job.createdAt) { $when = [string]$Job.createdAt }
    if ($when) {
        try {
            $t = [datetime]::Parse($when, $null, [Globalization.DateTimeStyles]::RoundtripKind)
            $age = [int]([datetime]::UtcNow - $t.ToUniversalTime()).TotalSeconds
            if ($age -gt $OrphanSec) { return $false }
            return $true
        }
        catch { }
    }
    return $true
}

function Filter-BobFleetLaneJobsLive {
    param(
        $Jobs,
        [int]$OrphanSec = 600
    )
    $out = @()
    foreach ($j in @(Normalize-BobPeerLaneJobsResult $Jobs)) {
        if (-not $j) { continue }
        if (Test-BobFleetJobProcessLive -Job $j -OrphanSec $OrphanSec) {
            $out += ,$j
        }
    }
    return $out
}

function Get-BobPeerLaneJobs {
    param(
        [string]$BridgeRoot,
        [string]$MachineId,
        [ValidateSet('running', 'inbox')][string]$Lane,
        [switch]$StampRepo,
        [int]$TimeoutMs = 0
    )
    $dir = Join-Path $BridgeRoot (Join-Path 'fleet' (Join-Path $Lane $MachineId))
    $effectiveMs = Get-BobPeekIoTimeoutMs -Path $dir -TimeoutMs $TimeoutMs
    $files = @()
    if ($effectiveMs -gt 0) {
        $r = Invoke-BobTimed -TimeoutMs $effectiveMs -ArgumentList @($dir) -Action {
            param($Dir)
            if (-not [IO.Directory]::Exists($Dir)) { return @() }
            return [IO.Directory]::GetFiles($Dir, '*.json')
        }
        if (-not $r.ok) { return $null }
        if ($null -eq $r.value) { $files = @() }
        elseif ($r.value -is [string]) { $files = @($r.value) }
        else { $files = @($r.value) }
    }
    else {
        if (Test-Path $dir) {
            $files = @(Get-ChildItem $dir -Filter '*.json' -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
        }
    }
    $rows = @()
    foreach ($f in $files) {
        if (-not $f) { continue }
        $j = $null
        if ($effectiveMs -gt 0) {
            $rr = Invoke-BobTimed -TimeoutMs $effectiveMs -ArgumentList @([string]$f) -Action {
                param($Path)
                if (-not [IO.File]::Exists($Path)) { return $null }
                $raw = [IO.File]::ReadAllText($Path)
                if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
                return ($raw | ConvertFrom-Json)
            }
            if (-not $rr.ok) { return $null }
            $j = $rr.value
        }
        else {
            $j = Read-JsonFile $f
        }
        $row = ConvertTo-BobPeekJob -Job $j -MachineId $MachineId -Lane $Lane -StampRepo:$StampRepo
        if ($row -and $row.id) { $rows += $row }
    }
    # Empty @() must not unroll to $null (idle inbox looked like I/O failure).
    return , $rows
}

function Read-BobJsonTimed {
    param([string]$Path, [int]$TimeoutMs)
    $effectiveMs = Get-BobPeekIoTimeoutMs -Path $Path -TimeoutMs $TimeoutMs
    if ($effectiveMs -le 0) {
        if (-not (Test-Path -LiteralPath $Path)) {
            return [pscustomobject]@{ ok = $true; timedOut = $false; value = $null; error = $null }
        }
        try {
            return [pscustomobject]@{ ok = $true; timedOut = $false; value = (Read-JsonFile $Path); error = $null }
        }
        catch {
            return [pscustomobject]@{ ok = $false; timedOut = $false; value = $null; error = $_.Exception.Message }
        }
    }
    $r = Invoke-BobTimed -TimeoutMs $effectiveMs -ArgumentList @($Path) -Action {
        param($P)
        if (-not [IO.File]::Exists($P)) { return $null }
        $raw = [IO.File]::ReadAllText($P)
        if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
        return ($raw | ConvertFrom-Json)
    }
    return $r
}

function Test-BobPathExistsTimed {
    param([string]$Path, [int]$TimeoutMs)
    $effectiveMs = Get-BobPeekIoTimeoutMs -Path $Path -TimeoutMs $TimeoutMs
    if ($effectiveMs -le 0) {
        return (Test-Path -LiteralPath $Path)
    }
    $r = Invoke-BobTimed -TimeoutMs $effectiveMs -ArgumentList @($Path) -Action {
        param($P)
        return ([IO.File]::Exists($P) -or [IO.Directory]::Exists($P))
    }
    if (-not $r.ok) { return $false }
    return [bool]$r.value
}

function ConvertTo-BobJsonString {
    param($Value)
    if ($null -eq $Value) { return 'null' }
    $s = [string]$Value
    $escaped = $s.Replace('\', '\\').Replace('"', '\"').Replace("`r", '\r').Replace("`n", '\n').Replace("`t", '\t')
    return '"' + $escaped + '"'
}

function ConvertTo-BobPeekJobJson {
    param($Job)
    if (-not $Job) { return $null }
    $parts = @()
    foreach ($k in @('id', 'machine', 'cwd', 'repo', 'claimedAt', 'createdAt', 'state', 'lane')) {
        $v = $Job.$k
        if ($null -eq $v -or [string]$v -eq '') { continue }
        $parts += ('"{0}":{1}' -f $k, (ConvertTo-BobJsonString $v))
    }
    if ($parts.Count -eq 0) { return $null }
    return '{' + ($parts -join ',') + '}'
}

function ConvertTo-BobPeekSnapshotJson {
    param(
        [string]$Id,
        [string]$Hostname,
        [string]$BridgeHome,
        [string]$WindowsUser,
        [string]$LastSeen,
        $Running,
        $Inbox
    )
    $runParts = New-Object 'System.Collections.Generic.List[string]'
    if ($Running) {
        foreach ($j in $Running) {
            if (-not $j) { continue }
            $p = ConvertTo-BobPeekJobJson $j
            if ($p) { [void]$runParts.Add($p) }
        }
    }
    $inParts = New-Object 'System.Collections.Generic.List[string]'
    if ($Inbox) {
        foreach ($j in $Inbox) {
            if (-not $j) { continue }
            $p = ConvertTo-BobPeekJobJson $j
            if ($p) { [void]$inParts.Add($p) }
        }
    }
    $fields = @(
        ('"id":{0}' -f (ConvertTo-BobJsonString $Id)),
        ('"hostname":{0}' -f (ConvertTo-BobJsonString $Hostname)),
        ('"bridgeHome":{0}' -f (ConvertTo-BobJsonString $BridgeHome)),
        ('"windowsUser":{0}' -f (ConvertTo-BobJsonString $WindowsUser)),
        ('"lastSeen":{0}' -f (ConvertTo-BobJsonString $LastSeen)),
        ('"running":[{0}]' -f ($runParts -join ',')),
        ('"inbox":[{0}]' -f ($inParts -join ','))
    )
    return '{' + ($fields -join ',') + '}'
}

function Get-BobSnapshotJobList {
    param($Prop)
    if ($null -eq $Prop) { return @() }
    $items = @($Prop)
    if ($items.Count -eq 0) { return @() }
    if ($items.Count -eq 1) {
        $one = $items[0]
        if ($null -eq $one) { return @() }
        $idVal = $null
        try { $idVal = $one.id } catch { }
        $isList = $false
        if ($idVal -is [System.Array]) { $isList = $true }
        elseif ($idVal -is [System.Collections.IEnumerable] -and $idVal -isnot [string]) { $isList = $true }
        if ($isList) {
            $ids = @($one.id)
            $macs = @($one.machine)
            $cwds = @($one.cwd)
            $repos = @($one.repo)
            $claimed = @($one.claimedAt)
            $created = @($one.createdAt)
            $states = @($one.state)
            $lanes = @($one.lane)
            $out = @()
            for ($i = 0; $i -lt $ids.Count; $i++) {
                $out += ,[pscustomobject]@{
                    id        = $(if ($i -lt $ids.Count) { [string]$ids[$i] } else { $null })
                    machine   = $(if ($i -lt $macs.Count) { [string]$macs[$i] } else { $null })
                    cwd       = $(if ($i -lt $cwds.Count) { [string]$cwds[$i] } else { $null })
                    repo      = $(if ($i -lt $repos.Count) { [string]$repos[$i] } else { $null })
                    claimedAt = $(if ($i -lt $claimed.Count) { $claimed[$i] } else { $null })
                    createdAt = $(if ($i -lt $created.Count) { $created[$i] } else { $null })
                    state     = $(if ($i -lt $states.Count) { [string]$states[$i] } else { $null })
                    lane      = $(if ($i -lt $lanes.Count) { [string]$lanes[$i] } else { $null })
                }
            }
            return $out
        }
    }
    return $items
}

function ConvertFrom-BobPeekSnapshot {
    param($Snap, [string]$MachineId)
    if (-not $Snap) { return $null }
    $id = $MachineId
    if ($Snap.id -and $Snap.id -is [string]) { $id = [string]$Snap.id }
    $jobs = New-Object 'System.Collections.Generic.List[object]'
    foreach ($j in @(Get-BobSnapshotJobList $Snap.running)) {
        $row = ConvertTo-BobPeekJob -Job $j -MachineId $id -Lane 'running'
        if ($row) { [void]$jobs.Add($row) }
    }
    foreach ($j in @(Get-BobSnapshotJobList $Snap.inbox)) {
        $row = ConvertTo-BobPeekJob -Job $j -MachineId $id -Lane 'inbox'
        if ($row) { [void]$jobs.Add($row) }
    }
    $seen = $null
    if ($Snap.lastSeen) { $seen = [string]$Snap.lastSeen }
    return [pscustomobject]@{
        ok       = $true
        id       = $id
        lastSeen = $seen
        hostname = $(if ($Snap.hostname) { [string]$Snap.hostname } else { $null })
        jobs     = $jobs
        source   = 'snapshot'
    }
}

function Read-BobPeerPeekFromPath {
    param(
        [string]$Id,
        [string]$Path,
        [int]$TimeoutMs
    )
    if (-not $Path) { return $null }
    if (-not (Test-BobPathExistsTimed -Path $Path -TimeoutMs $TimeoutMs)) { return $null }

    $isJson = $false
    if ($Path -match '\.json$') { $isJson = $true }
    if ($isJson) {
        $r = Read-BobJsonTimed -Path $Path -TimeoutMs $TimeoutMs
        if (-not $r.ok) { return $null }
        if ($null -eq $r.value) { return $null }
        return (ConvertFrom-BobPeekSnapshot -Snap $r.value -MachineId $Id)
    }

    $snapPath = Join-Path $Path (Join-Path 'fleet' (Join-Path 'peek' ($Id + '.json')))
    if (Test-BobPathExistsTimed -Path $snapPath -TimeoutMs $TimeoutMs) {
        $r = Read-BobJsonTimed -Path $snapPath -TimeoutMs $TimeoutMs
        if ($r.ok -and $r.value) {
            return (ConvertFrom-BobPeekSnapshot -Snap $r.value -MachineId $Id)
        }
    }

    $machinePath = Join-Path $Path 'machine.json'
    $seen = $null
    $hostName = $null
    if (Test-BobPathExistsTimed -Path $machinePath -TimeoutMs $TimeoutMs) {
        $mr = Read-BobJsonTimed -Path $machinePath -TimeoutMs $TimeoutMs
        if (-not $mr.ok) { return $null }
        if ($mr.value) {
            if ($mr.value.lastSeen) { $seen = [string]$mr.value.lastSeen }
            if ($mr.value.hostname) { $hostName = [string]$mr.value.hostname }
        }
    }

    $running = Get-BobPeerLaneJobs -BridgeRoot $Path -MachineId $Id -Lane running -TimeoutMs $TimeoutMs
    if ($null -eq $running) { return $null }
    $inbox = Get-BobPeerLaneJobs -BridgeRoot $Path -MachineId $Id -Lane inbox -TimeoutMs $TimeoutMs
    if ($null -eq $inbox) { return $null }

    $jobs = @()
    foreach ($j in @($running)) { if ($j) { $jobs += $j } }
    foreach ($j in @($inbox)) { if ($j) { $jobs += $j } }
    return [pscustomobject]@{
        ok       = $true
        id       = $Id
        lastSeen = $seen
        hostname = $hostName
        jobs     = $jobs
        source   = 'bridge-home'
    }
}

function Get-BobPeerPeekCandidates {
    param($Spec, [string]$ShareRoot)
    $out = @()
    if ($Spec.peekRoot -and [string]$Spec.peekRoot.Trim()) {
        $out += [string]$Spec.peekRoot.Trim()
    }
    if ($ShareRoot -and [string]$ShareRoot.Trim()) {
        $out += (Join-Path ([string]$ShareRoot.Trim()) ($Spec.id + '.json'))
    }
    # Do not probe \\hostname\C$ from the tray. DNS/SMB misses block 15-30s even
    # after a timeout wrapper, so idle hover never paints the machine tiles.
    # Cross-host jobs need peekRoot or BOB_FLEET_SHARE (docs/bob-fleet-peer-peek.md).
    $seen = @{}
    $uniq = @()
    foreach ($p in $out) {
        if (-not $p) { continue }
        $k = $p.ToLowerInvariant()
        if ($seen.ContainsKey($k)) { continue }
        $seen[$k] = $true
        $uniq += $p
    }
    return $uniq
}

function Read-BobPeerPeek {
    param(
        [Parameter(Mandatory)][string]$Id,
        $Spec,
        [string]$ShareRoot,
        [int]$TimeoutMs = 1500
    )
    $fail = [pscustomobject]@{
        ok       = $false
        id       = $Id
        lastSeen = $null
        hostname = $(if ($Spec) { [string]$Spec.hostname } else { $null })
        jobs     = @()
        source   = 'unreachable'
        error    = 'unreachable'
    }
    $candidates = @(Get-BobPeerPeekCandidates -Spec $Spec -ShareRoot $ShareRoot)
    foreach ($c in $candidates) {
        try {
            $got = Read-BobPeerPeekFromPath -Id $Id -Path $c -TimeoutMs $TimeoutMs
            if ($got -and $got.ok) { return $got }
        }
        catch { }
    }
    try {
        $irc = Read-BobIrcPeer -Id $Id
        if ($irc -and $irc.ok) { return $irc }
    }
    catch { }
    return $fail
}

function Write-BobFleetPeekSnapshot {
    $id = Get-ThisMachineId
    if (-not $id) { return }
    $root = Get-BridgeRoot
    $rec = Read-JsonFile (Join-Path $root 'machine.json')
    $running = Get-BobPeerLaneJobs -BridgeRoot $root -MachineId $id -Lane running -StampRepo
    if ($null -eq $running) { $running = New-Object 'System.Collections.Generic.List[object]' }
    $inbox = Get-BobPeerLaneJobs -BridgeRoot $root -MachineId $id -Lane inbox -StampRepo
    if ($null -eq $inbox) { $inbox = New-Object 'System.Collections.Generic.List[object]' }
    $seen = [DateTime]::UtcNow.ToString('o')
    if ($rec -and $rec.lastSeen) { $seen = [string]$rec.lastSeen }
    $peekDir = Join-Path (Initialize-FleetRoot) 'peek'
    New-Item -ItemType Directory -Force -Path $peekDir | Out-Null
    # Never assign job arrays as PSCustomObject properties: PS 5.1 collapses them.
    $snapJson = ConvertTo-BobPeekSnapshotJson -Id $id -Hostname $env:COMPUTERNAME `
        -BridgeHome $root -WindowsUser "$env:USERDOMAIN\$env:USERNAME" -LastSeen $seen `
        -Running $running -Inbox $inbox
    [IO.File]::WriteAllText((Join-Path $peekDir ($id + '.json')), $snapJson)

    $share = $null
    if ($env:BOB_FLEET_SHARE -and $env:BOB_FLEET_SHARE.Trim()) {
        $share = $env:BOB_FLEET_SHARE.Trim()
    }
    else {
        try {
            $localReg = Read-JsonFile (Join-Path (Get-FleetRoot) 'registry.json')
            if ($localReg -and $localReg.shareRoot) { $share = [string]$localReg.shareRoot }
        }
        catch { }
    }
    if ($share) {
        try {
            New-Item -ItemType Directory -Force -Path $share | Out-Null
            [IO.File]::WriteAllText((Join-Path $share ($id + '.json')), $snapJson)
        }
        catch { }
    }
    Write-BobFleetRegistrySelf
    Write-BobFleetMachineStubs
}
