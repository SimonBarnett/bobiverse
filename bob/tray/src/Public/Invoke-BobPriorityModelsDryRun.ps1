# FR #8696 / BOB-51: Priority launch dry-run cites models webhook Priority row.

function Invoke-BobPriorityModelsDryRun {
    [CmdletBinding()]
    param(
        [string]$Uri,
        [string]$FixturePath,
        [string]$FixtureJson,
        [string]$LogPath,
        [switch]$Quiet
    )
    if (-not $Uri) { $Uri = Get-BobModelsWebhookUri }
    $row = Get-BobModelsWebhookAgentRow -AgentId 'priority' -Uri $Uri -FixturePath $FixturePath -FixtureJson $FixtureJson
    if (-not $row) {
        throw "BOB-51: models webhook has no Priority row (uri=$Uri)"
    }
    $model = ''
    $context = ''
    $effort = ''
    $cli = ''
    if ($row.PSObject.Properties.Name -contains 'model') { $model = [string]$row.model }
    if ($row.PSObject.Properties.Name -contains 'context') { $context = [string]$row.context }
    if ($row.PSObject.Properties.Name -contains 'effort') { $effort = [string]$row.effort }
    if ($row.PSObject.Properties.Name -contains 'cli') { $cli = [string]$row.cli }
    if (-not $LogPath) {
        $override = [string]$env:BOB_PRIORITY_MODELS_DRYRUN_LOG
        if ($override -and $override.Trim().Length -gt 0) {
            $LogPath = $override.Trim()
        }
        else {
            $base = Join-Path $env:LOCALAPPDATA 'Bobiverse\logs'
            if (-not (Test-Path -LiteralPath $base)) {
                New-Item -ItemType Directory -Force -Path $base | Out-Null
            }
            $LogPath = Join-Path $base 'priority-models-dry-run.log'
        }
    }
    $parent = Split-Path -Parent $LogPath
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $ts = (Get-Date).ToUniversalTime().ToString('o')
    $lines = @(
        "ts=$ts",
        'fr=8696',
        'bob=BOB-51',
        'agent=priority',
        ("webhook=" + $Uri),
        ("cli=" + $cli),
        ("model=" + $model),
        ("context=" + $context),
        ("effort=" + $effort),
        'launch=dry-run',
        'source=models-webhook-priority-row'
    )
    $text = ($lines -join [Environment]::NewLine) + [Environment]::NewLine
    [IO.File]::WriteAllText($LogPath, $text, (New-Object System.Text.UTF8Encoding $false))
    if (-not $Quiet) {
        Write-Output $text.TrimEnd()
    }
    return [pscustomobject]@{
        Agent    = 'priority'
        Webhook  = $Uri
        Model    = $model
        Context  = $context
        Effort   = $effort
        Cli      = $cli
        LogPath  = $LogPath
        DryRun   = $true
    }
}