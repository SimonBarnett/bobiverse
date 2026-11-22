# FR #8696 / BOB-51: models webhook client (Priority row). WinPS 5.1.
# Public digest/models producer is BOB-01; this consumer accepts live GET or fixture.

function Get-BobModelsWebhookUri {
    [CmdletBinding()]
    param()
    $fromEnv = [string]$env:BOB_MODELS_WEBHOOK_URL
    if ($fromEnv -and $fromEnv.Trim().Length -gt 0) {
        return $fromEnv.Trim().TrimEnd('/')
    }
    return 'https://bob.ntsa.uk/bob/v1/models'
}

function Get-BobModelsWebhookDocument {
    [CmdletBinding()]
    param(
        [string]$Uri,
        [string]$FixturePath,
        [string]$FixtureJson
    )
    if ($FixtureJson -and $FixtureJson.Trim().Length -gt 0) {
        return $FixtureJson | ConvertFrom-Json
    }
    if ($FixturePath -and (Test-Path -LiteralPath $FixturePath)) {
        $raw = [IO.File]::ReadAllText($FixturePath)
        return $raw | ConvertFrom-Json
    }
    $fixtureEnv = [string]$env:BOB_MODELS_WEBHOOK_FIXTURE
    if ($fixtureEnv -and (Test-Path -LiteralPath $fixtureEnv)) {
        $raw = [IO.File]::ReadAllText($fixtureEnv)
        return $raw | ConvertFrom-Json
    }
    if (-not $Uri) { $Uri = Get-BobModelsWebhookUri }
    # Prefer existing digest HTTP helper when present (no secrets).
    if (Get-Command Invoke-BobDigestHttpGet -ErrorAction SilentlyContinue) {
        $r = Invoke-BobDigestHttpGet -Uri $Uri
        if ($r -and $r.Parsed) { return $r.Parsed }
        if ($r -and $r.Body) { return ($r.Body | ConvertFrom-Json) }
    }
    $resp = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 15
    return ($resp.Content | ConvertFrom-Json)
}

function Get-BobModelsWebhookAgentRow {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$AgentId,
        $Document,
        [string]$Uri,
        [string]$FixturePath,
        [string]$FixtureJson
    )
    if (-not $Document) {
        $Document = Get-BobModelsWebhookDocument -Uri $Uri -FixturePath $FixturePath -FixtureJson $FixtureJson
    }
    if (-not $Document) { return $null }
    $want = $AgentId.Trim().ToLowerInvariant()
    $rows = @()
    if ($Document.agents) { $rows = @($Document.agents) }
    elseif ($Document.PSObject.Properties.Name -contains 'agent_rows') { $rows = @($Document.agent_rows) }
    foreach ($row in $rows) {
        if (-not $row) { continue }
        $id = ''
        if ($row.PSObject.Properties.Name -contains 'id') { $id = [string]$row.id }
        elseif ($row.PSObject.Properties.Name -contains 'agent') { $id = [string]$row.agent }
        elseif ($row.PSObject.Properties.Name -contains 'name') { $id = [string]$row.name }
        if ($id.Trim().ToLowerInvariant() -eq $want) { return $row }
    }
    return $null
}