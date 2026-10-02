function Get-FleetRoot {
    Join-Path (Get-BridgeRoot) 'fleet'
}

function Initialize-FleetRoot {
    $root = Get-FleetRoot
    foreach ($n in @('inbox', 'running', 'outbox', 'machines', 'cancel', 'followup', 'peek')) {
        New-Item -ItemType Directory -Force -Path (Join-Path $root $n) | Out-Null
    }
    return $root
}

function ConvertTo-MachineId {
    param([Parameter(Mandatory)][string]$Name)
    $id = $Name.Trim().ToLowerInvariant()
    if ($id -notmatch '^[a-z0-9][a-z0-9-]{0,62}$') {
        throw "invalid machine id '$Name'"
    }
    return $id
}

function Get-FleetJobPath {
    param(
        [Parameter(Mandatory)][ValidateSet('inbox', 'running', 'outbox', 'cancel')][string]$Lane,
        [Parameter(Mandatory)][string]$Machine,
        [Parameter(Mandatory)][string]$JobId
    )
    $mid = ConvertTo-MachineId $Machine
    $dir = Join-Path (Initialize-FleetRoot) (Join-Path $Lane $mid)
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    Join-Path $dir ($JobId + '.json')
}

function Read-FleetJob {
    param([Parameter(Mandatory)][string]$JobId)
    $root = Initialize-FleetRoot
    foreach ($lane in @('running', 'inbox', 'outbox')) {
        $hits = @(Get-ChildItem (Join-Path $root $lane) -Recurse -Filter ($JobId + '.json') -ErrorAction SilentlyContinue)
        if ($hits.Count -gt 0) {
            $job = Read-JsonFile $hits[0].FullName
            if ($job) {
                $job | Add-Member -NotePropertyName lane -NotePropertyValue $lane -Force
                $job | Add-Member -NotePropertyName path -NotePropertyValue $hits[0].FullName -Force
                return $job
            }
        }
    }
    return $null
}

function Test-CwdAllowed {
    param(
        [Parameter(Mandatory)][string]$Cwd,
        $MachineRecord
    )
    if (-not $MachineRecord -or -not $MachineRecord.cwdRoots) { return $true }
    $full = [IO.Path]::GetFullPath($Cwd)
    foreach ($root in @($MachineRecord.cwdRoots)) {
        if (-not $root) { continue }
        try { $r = [IO.Path]::GetFullPath([string]$root) }
        catch { continue }
        if ($full.StartsWith($r, [StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    return $false
}

function New-FleetPrompt {
    param($Packet)
    $lines = New-Object System.Collections.Generic.List[string]
    [void]$lines.Add("Goal: $($Packet.goal)")
    if ($Packet.success) { [void]$lines.Add("Success: $($Packet.success)") }
    $cons = @($Packet.constraints)
    if ($cons.Count -gt 0) {
        [void]$lines.Add('Constraints:')
        foreach ($c in $cons) { [void]$lines.Add("- $c") }
    }
    [void]$lines.Add("Machine: $($Packet.machine)")
    if ($Packet.fuel) { [void]$lines.Add("Fuel: $($Packet.fuel)") }
    if ($Packet.task) { [void]$lines.Add("Task: $($Packet.task)") }
    [void]$lines.Add("Cwd: $($Packet.cwd)")
    [void]$lines.Add("Profile: $($Packet.profile)")
    if ($Packet.model) { [void]$lines.Add("Model: $($Packet.model)") }
    if ($Packet.kind) { [void]$lines.Add("Kind: $($Packet.kind)") }
    if ($Packet.repo) { [void]$lines.Add("Repo: $($Packet.repo)") }
    if ($Packet.branch) { [void]$lines.Add("Branch: $($Packet.branch)") }
    if ($Packet.docs) { [void]$lines.Add("Docs: $($Packet.docs)") }
    if ($Packet.plan) { [void]$lines.Add("Plan: $($Packet.plan)") }
    if ($Packet.mrb) { [void]$lines.Add("Mrb: $($Packet.mrb)") }
    [void]$lines.Add('MSSQL: Windows integrated auth as the logon user. No SQL passwords.')
    [void]$lines.Add('GitHub repo coding: tools/Start-BobCopilot.ps1 (skill start-bob-copilot). Do not use Grok Bot weekly usage for that work.')
    if ([string]$Packet.task -eq 'git') {
        [void]$lines.Add('IRC verbs (no vendor names): SPEC WAIT BUILD PUSH MRB FIX UAT.')
        [void]$lines.Add('Open a PR from the work branch. Never push main. Never merge. Do not mark ready for human UAT. Bob chairs UAT.')
        if ([string]$Packet.kind -eq 'mrb') {
            [void]$lines.Add('MRB: PASS-nits merge the PR (nits do not block). FAIL do not merge; Required fixes only. Dispatcher starts the FIX worker.')
        }
        if ([string]$Packet.fuel -eq 'cursor-models') {
            [void]$lines.Add('Fuel cursor-models: tools/Start-BobCursor.ps1 (skill start-bob-cursor). Do not start grok.exe.')
        }
    }
    [void]$lines.Add((Get-BobProjectSkillsHint))
    return ($lines -join "`n")
}

function Write-FleetHeartbeat {
    $id = Get-ThisMachineId
    if (-not $id) { return }
    $path = Join-Path (Get-BridgeRoot) 'machine.json'
    $rec = Read-JsonFile $path
    if (-not $rec) { return }
    $rec | Add-Member -NotePropertyName lastSeen -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
    $rec | Add-Member -NotePropertyName windowsUser -NotePropertyValue "$env:USERDOMAIN\$env:USERNAME" -Force
    $rec = Update-BobMachineGhPostingSnapshot -Record $rec
    Write-JsonFile $path $rec
    Write-JsonFile (Join-Path (Initialize-FleetRoot) (Join-Path 'machines' ($id + '.json'))) $rec
    try { Write-BobFleetPeekSnapshot } catch { }
}

function Test-FleetCancel {
    param([string]$Machine, [string]$JobId)
    Test-Path (Get-FleetJobPath -Lane cancel -Machine $Machine -JobId $JobId)
}

function Set-BobFleetPacketPrUrlIfKnown {
    param(
        $Packet,
        $Completion
    )
    if (-not $Packet) { return }
    if ($Packet.prUrl) { return }
    $pr = $null
    if ($Completion -and $Completion.evidence -and $Completion.evidence.prUrl) {
        $pr = [string]$Completion.evidence.prUrl
    }
    elseif ($Completion -and $Completion.summary -match '(https://github\.com/[\w.-]+/[\w.-]+/pull/\d+)') {
        $pr = $Matches[1]
    }
    if ($pr) {
        $Packet | Add-Member -NotePropertyName prUrl -NotePropertyValue $pr -Force
    }
}

function Complete-FleetJob {
    param(
        $Packet,
        [string]$FromPath,
        [string]$State,
        $Completion,
        [string]$SessionId
    )
    Write-FleetHeartbeat
    $packet = $Packet
    $packet | Add-Member -NotePropertyName state -NotePropertyValue $State -Force
    $packet | Add-Member -NotePropertyName completedAt -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
    if ($Completion) { $packet | Add-Member -NotePropertyName completion -NotePropertyValue $Completion -Force }
    if ($SessionId) { $packet | Add-Member -NotePropertyName sessionId -NotePropertyValue $SessionId -Force }
    $out = Get-FleetJobPath -Lane outbox -Machine $packet.machine -JobId $packet.id
    Write-JsonFile $out $packet
    if ($FromPath -and (Test-Path $FromPath)) {
        Remove-Item -Force $FromPath -ErrorAction SilentlyContinue
    }
    $follow = Join-Path (Initialize-FleetRoot) (Join-Path 'followup' (Join-Path $packet.machine ($packet.id + '.json')))
    if (Test-Path $follow) { Remove-Item -Force $follow -ErrorAction SilentlyContinue }
    Send-FleetReply -ReplyChannel $packet.reply_channel -Text "$($packet.machine) $State $($packet.id): $(if ($Completion) { $Completion.summary } else { $State })"
    Set-BobFleetPacketPrUrlIfKnown -Packet $packet -Completion $Completion
    $auditStatus = $State
    if ($Completion -and $Completion.status) { $auditStatus = [string]$Completion.status }
    Write-BobJobAuditFromPacket -Packet $packet -Status $auditStatus
    return $packet
}

function Invoke-BobFleetTick {
    try { Invoke-BobRepoPairChairTick | Out-Null } catch { }
    return Invoke-BobFleetOnce
}

function Invoke-BobFleetOnce {
    $thisId = Get-ThisMachineId
    if (-not $thisId) {
        return [pscustomobject]@{ ok = $false; error = 'machine_unregistered' }
    }
    Write-FleetHeartbeat
    $inboxDir = Join-Path (Initialize-FleetRoot) (Join-Path 'inbox' $thisId)
    New-Item -ItemType Directory -Force -Path $inboxDir | Out-Null
    $files = @(Get-ChildItem $inboxDir -Filter '*.json' -ErrorAction SilentlyContinue | Sort-Object Name)
    if ($files.Count -eq 0) {
        return [pscustomobject]@{ ok = $true; claimed = $false }
    }
    $file = $files[0]
    $packet = Read-JsonFile $file.FullName
    if (-not $packet) {
        Remove-Item -Force $file.FullName
        return [pscustomobject]@{ ok = $false; error = 'bad_packet' }
    }

    if (Test-FleetCancel -Machine $thisId -JobId $packet.id) {
        return Complete-FleetJob -Packet $packet -FromPath $file.FullName -State 'stopped'
    }

    $self = Read-JsonFile (Join-Path (Get-BridgeRoot) 'machine.json')
    if (-not (Test-CwdAllowed -Cwd $packet.cwd -MachineRecord $self)) {
        $comp = [pscustomobject]@{ status = 'failed'; summary = 'cwd_not_allowed'; needs_human = $true }
        return Complete-FleetJob -Packet $packet -FromPath $file.FullName -State 'failed' -Completion $comp
    }

    $missingFuel = Test-BobPacketMissingFuel -Fuel $packet.fuel -Model $packet.model
    if (-not $missingFuel.ok) {
        $comp = [pscustomobject]@{ status = 'failed'; summary = $missingFuel.summary; needs_human = $true }
        return Complete-FleetJob -Packet $packet -FromPath $file.FullName -State 'failed' -Completion $comp
    }

    $fuelModel = [pscustomobject]@{ ok = $true; summary = $null }
    if ($packet.fuel) {
        $fuelModel = Test-BobFuelModelCompatible -Fuel $packet.fuel -Model $packet.model
    }
    if (-not $fuelModel.ok) {
        $comp = [pscustomobject]@{ status = 'failed'; summary = $fuelModel.summary; needs_human = $true }
        return Complete-FleetJob -Packet $packet -FromPath $file.FullName -State 'failed' -Completion $comp
    }

    $runningPath = Get-FleetJobPath -Lane running -Machine $thisId -JobId $packet.id
    Move-Item -Force $file.FullName $runningPath
    $packet | Add-Member -NotePropertyName state -NotePropertyValue 'running' -Force
    $packet | Add-Member -NotePropertyName claimedAt -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
    Write-JsonFile $runningPath $packet
    Send-FleetReply -ReplyChannel $packet.reply_channel -Text "$thisId running $($packet.id)"

    $fuel = [string]$packet.fuel
    $task = [string]$packet.task
    $useGrokExe = -not ($task -eq 'git' -and $fuel -and ($fuel -notin @('grok-build', 'on-demand')))
    if (-not $useGrokExe) {
        $summary = "handed $fuel"
        $status = 'ok'
        if ($fuel -eq 'cursor-models') {
            $cursorScript = Join-Path (Get-ModuleRoot) 'tools\Start-BobCursor.ps1'
            if (Test-Path $cursorScript) {
                try {
                    $cursorArgs = @{ Job = $packet }
                    if ($packet.kind) { $cursorArgs['Kind'] = [string]$packet.kind }
                    if (Test-BobUsesFakeGrok) { $cursorArgs['NoLaunch'] = $true }
                    $hand = & $cursorScript @cursorArgs
                    if ($hand -and $hand.packetPath) { $summary = "handed cursor-models $($hand.packetPath)" }
                }
                catch {
                    $status = 'failed'
                    $summary = "cursor-models handoff failed: $($_.Exception.Message)"
                }
            }
        }
        elseif ($fuel -eq 'copilot') {
            $copilotScript = Join-Path (Get-ModuleRoot) 'tools\Start-BobCopilot.ps1'
            $summary = 'handed copilot (start-bob-copilot)'
            if ((Test-Path $copilotScript) -and -not (Test-BobUsesFakeGrok) -and $packet.mrb) {
                try {
                    $hand = & $copilotScript -Prompt $packet.goal
                    if ($hand -and $hand.issue) { $summary = "handed copilot $($hand.issue)" }
                }
                catch {
                    $status = 'failed'
                    $summary = "copilot handoff failed: $($_.Exception.Message)"
                }
            }
        }
        $comp = [pscustomobject]@{ status = $status; summary = $summary; needs_human = ($status -ne 'ok') }
        return Complete-FleetJob -Packet $packet -FromPath $runningPath -State $(if ($status -eq 'ok') { 'done' } else { 'failed' }) -Completion $comp
    }

    $prompt = New-FleetPrompt -Packet $packet
    $start = Start-BobWorker -Cwd $packet.cwd -Prompt $prompt -Profile $packet.profile -Title "fleet-$($packet.id)" -SessionId $packet.id -Model $packet.model -Force
    $sessionId = $start.sessionId

    $followPath = Join-Path (Initialize-FleetRoot) (Join-Path 'followup' (Join-Path $thisId ($packet.id + '.json')))
    if ((Test-Path $followPath) -and $sessionId) {
        $follows = Read-JsonFile $followPath
        foreach ($item in @($follows)) {
            if (Test-FleetCancel -Machine $thisId -JobId $packet.id) { break }
            $p = $item.prompt
            if (-not $p) { $p = [string]$item }
            if ($p) { Send-BobPrompt -SessionId $sessionId -Prompt $p | Out-Null }
        }
    }

    if (Test-FleetCancel -Machine $thisId -JobId $packet.id) {
        try { Stop-BobWorker -SessionId $sessionId | Out-Null } catch { }
        return Complete-FleetJob -Packet $packet -FromPath $runningPath -State 'stopped' -Completion $start.completion -SessionId $sessionId
    }

    $state = 'done'
    if ($start.completion -and $start.completion.status -eq 'stopped') { $state = 'stopped' }
    elseif ($start.completion -and $start.completion.status -eq 'failed') { $state = 'failed' }
    elseif ($start.completion -and $start.completion.status -eq 'blocked') { $state = 'blocked' }
    elseif (-not $start.ok) { $state = 'failed' }
    return Complete-FleetJob -Packet $packet -FromPath $runningPath -State $state -Completion $start.completion -SessionId $sessionId
}

function Send-FleetReply {
    param(
        [string]$ReplyChannel,
        [string]$Text
    )
    if (-not $ReplyChannel) { return }
    if (Test-BobUsesFakeGrok) { return }
    if (-not (Test-GrokBotAvailable)) { return }
    try {
        Invoke-GrokBotApi -Action send -Agent $ReplyChannel -Text $Text -TimeoutSec 60 | Out-Null
    }
    catch { }
}
