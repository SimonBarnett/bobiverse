$PublicDir  = Join-Path $PSScriptRoot 'Public'
$PrivateDir = Join-Path $PSScriptRoot 'Private'

# FR #9187: if install src\Private\Invoke-BobFleet.ps1 was dollar-stripped by a
# tray hotpatch (fed44b9b / a1a94bd7), try one heal from sibling bob\tray before
# dot-sourcing (Import-Module otherwise floods parse errors every engine-step).
$fleetLive = Join-Path $PrivateDir 'Invoke-BobFleet.ps1'
if (Test-Path -LiteralPath $fleetLive) {
    $fleetText = [IO.File]::ReadAllText($fleetLive)
    if ([regex]::IsMatch($fleetText, 'param\s*\(\s*\[string\]\s*\)')) {
        $installRoot = Split-Path -Parent $PSScriptRoot
        $healCandidates = @(
            (Join-Path $installRoot 'bob\tray\src\Private\Invoke-BobFleet.ps1'),
            (Join-Path $PSScriptRoot '..\..\tray\src\Private\Invoke-BobFleet.ps1')
        )
        $healed = $false
        foreach ($cand in $healCandidates) {
            if (-not (Test-Path -LiteralPath $cand)) { continue }
            $candText = [IO.File]::ReadAllText($cand)
            if ([regex]::IsMatch($candText, 'param\s*\(\s*\[string\]\s*\)')) { continue }
            if ($candText -notmatch 'param\(\[string\]\$Body\)') { continue }
            $tokens = $null; $errs = $null
            [void][System.Management.Automation.Language.Parser]::ParseFile($cand, [ref]$tokens, [ref]$errs)
            if (@($errs).Count -gt 0) { continue }
            Copy-Item -LiteralPath $cand -Destination $fleetLive -Force
            $healed = $true
            break
        }
        if (-not $healed) {
            throw 'FR #9187: Invoke-BobFleet.ps1 has nameless param([string]); Sync or tray hotpatch from a tip that keeps $Body/$Issue (see FR #8877/#9035).'
        }
    }
}

Get-ChildItem -Path $PrivateDir -Filter '*.ps1' -ErrorAction Stop | ForEach-Object {
    . $_.FullName
}
Get-ChildItem -Path $PublicDir -Filter '*.ps1' -ErrorAction Stop | ForEach-Object {
    . $_.FullName
}

Export-ModuleMember -Function @(
    'Get-BobHealth',
    'Get-BobGhPostingReadiness',
    'Report-BobDeterministicException',
    'Get-BobDeterministicExceptionOwningRepo',
    'Install-BobGitHubCliIfMissing',
    'Get-BobWorkers',
    'Get-BobAgents',
    'Get-BobMachines',
    'Register-BobMachine',
    'Start-BobWorker',
    'Start-BobBuild',
    'Get-BobCapacity',
    'Get-BobGrokAuthSnapshot',
    'Get-BobGrokAvailability',
    'Get-BobJobModel',
    'Invoke-BobPriorityModelsDryRun',
    'Get-BobModelsWebhookUri',
    'Get-BobModelsWebhookDocument',
    'Get-BobModelsWebhookAgentRow',
    'Test-BobFuelHasIncluded',
    'Test-BobFuelModelCompatible',
    'Test-BobPacketMissingFuel',
    'Resolve-BobGrokCliModel',
    'Select-BobGitWorker',
    'Get-BobBuildLoopCurrentJob',
    'Set-BobBuildLoopCurrentJob',
    'Test-BobFrBodyDispatched',
    'Test-BobQuotaFailureText',
    'Sync-BobShopChannelRepoDescriptions',
    'Get-ThisMachineId',
    'Copy-BobProjectSkills',
    'Get-BobBuild',
    'Get-BobBuilds',
    'Send-BobBuildSpec',
    'Stop-BobBuild',
    'Invoke-BobFleetTick',
    'Send-BobPrompt',
    'Get-BobStatus',
    'Get-BobResult',
    'Stop-BobWorker',
    'Export-BobTranscript',
    'Get-BobStallAlerts',
    'Invoke-BobQueueIntervene',
    'Get-BobStallFrIntake',
    'Get-BobTrayHover',
    'Get-BobTrayDigestPoolCatalog',
    'Format-BobTrayDigestPoolHeading',
    'Update-BobTrayDigestPools',
    'Invoke-BobDigestHttpGet',
    'Format-BobTrayXaiWeeklyRow',
    'Select-BobTrayXaiWeeklyFromDigestNode',
    'Format-BobPeerPoolHeading',
        'Resolve-BobCursorXaiSharedPools',
        'Get-BobSharedCursorXaiAggregateRemaining',
        'Format-BobCursorXaiSharedPoolTitle',
        'Get-BobSharedCursorXaiRemainingFromCapacity',
    'Expand-BobReportDigestView',
    'Test-BobTrayWorkerNickKey',
    'New-BobTrayIrcWorkerJobRow',
    'Get-BobCursorOverageGbp',
    'Get-BobSeatForMachine',
    'Get-BobSeatConfig',
    'Format-BobCursorAccountLabel',
    'Test-BobCursorOverageLabel',
    'Test-BobLiveGrokIsFleetSeat',
    'Get-BobLiveGrokAgents',
    'Get-BobTrayBarPaint',
    'Get-BobTrayBarFillRgb',
    'Get-BobTrayAlertKind',
    'Get-BobTrayTitle',
    'Get-BobTrayCursorGroupHelpTooltip',
    'Get-BobWeeklyRemaining',
    'Get-BobCursorAgentWeeklyRemaining',
    'Get-BobCursorGroupRemainFromLocalDoc',
    'Get-BobCursorSpendingFromApiFixture',
    'Get-BobTrayTipPlacement',
    'Get-BobTrayCursorTipPlacement',
    'Test-BobTrayRectIntersectsAny',
    'Test-BobTrayIconRectUsable',
    'ConvertTo-BobTrayRect',
    'Get-BobFleetRegistry',
    'ConvertTo-BobIrcPoint',
    'ConvertFrom-BobIrcPoint',
    'Read-BobIrcPeer',
    'Write-BobIrcStatus',
    'Import-BobIrcPeerTranscript',
    'Import-BobIrcTrayPull',
    'Import-BobWorkerGitShop',
    'Invoke-BobWorkerShopTick',
    'ConvertFrom-BobGitAnnounce',
    'ConvertFrom-BobGitTask',
    'Test-BobGitBoredNak',
    'Get-BobGitUnaccepted',
    'Send-BobGitWorkActivity',
    'Start-BobGitAcceptWork',
    'Test-BobGitAcceptWorkerBusy',
    'Request-BobIrcBobiversePull',
    'Sync-BobDigestWebhookAfterBobiversePull',
    'ConvertFrom-BobIrcTrayLine',
    'Get-BobJobRepoStamp',
    'Resolve-BobiverseMachineId',
    'Get-BobCanonicalMachineId',
    'Select-BobUniqueCanonicalIds',
    'Get-BobIrcShopChannel',
    'Get-BobIrcBuilderChannels',
    'Get-BobWorkerIrcNick',
    'Compact-BobIrcOutbox',
    'Write-BobJobAuditLine',
    'Write-BobJobAuditFromPacket',
    'Invoke-BobGrokTalkTick',
    'Test-BobGrokTalkFuelAllowed',
    'Select-BobGrokTalkFuel',
    'Add-BobGrokTalkCompletion',
    'ConvertTo-BobGrokTalkOutLines',
    'Get-BobRepoPair',
    'Start-BobRepoPair',
    'Invoke-BobRepoPairTick',
    'Invoke-BobRepoPairChairTick',
    'Assign-BobRepoPairTask',
    'Invoke-BobRepoPairOutstandingTickets',
    'Invoke-BobRepoPairBobiverseSay',
    'Update-BobRepoWorkerWorkingOn',
    'Test-BobRepoPairSelfMrb',
    'Test-BobRepoPairSeatAlive',
    'Test-BobRepoPairMayEnqueueBuild',
    'Set-BobRepoPairDevActiveSha',
    'Register-BobRepoPairDevComplete',
    'Register-BobRepoPairMrbComplete',
    'Get-BobRepoPairBobiverseReport',
    'Set-BobShopChannelRepoDescription',
    'Invoke-BobDigestWebhookPost',
    'Invoke-BobRepoPairChairUsageWebhookIfChanged',
    'Start-BobRepoPairMrbReview',
    'Test-BobRepoPairTicketCadenceDue'
)
