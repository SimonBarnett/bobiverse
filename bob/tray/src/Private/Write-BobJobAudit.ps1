function Write-BobJobAuditLine {
    param(
        [Parameter(Mandatory)][string]$JobId,
        [string]$Machine,
        [string]$Fuel,
        [string]$Model,
        [string]$Kind,
        [string]$PrUrl,
        [string]$MrbIssue,
        [string]$Sha,
        [Parameter(Mandatory)][string]$Status
    )
    $root = Initialize-BridgeRoot
    $path = Join-Path $root 'job-audit.jsonl'
    $row = [ordered]@{
        jobId     = [string]$JobId
        machine   = [string]$Machine
        fuel      = [string]$Fuel
        model     = [string]$Model
        kind      = [string]$Kind
        prUrl     = [string]$PrUrl
        mrbIssue  = [string]$MrbIssue
        sha       = [string]$Sha
        status    = [string]$Status
        time      = [DateTime]::UtcNow.ToString('o')
    }
    $line = ($row | ConvertTo-Json -Compress)
    if ($line -match 'XAI_API_KEY|password\s*=') {
        throw 'Refusing to write job-audit line that looks like a secret assignment'
    }
    # FR #347: UTF-8 without BOM
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [IO.File]::AppendAllText($path, $line + [Environment]::NewLine, $utf8)
}

function Write-BobJobAuditFromPacket {
    param(
        $Packet,
        [Parameter(Mandatory)][string]$Status
    )
    if (-not $Packet) { return }
    $pr = ''
    if ($Packet.prUrl) { $pr = [string]$Packet.prUrl }
    $mrb = ''
    if ($Packet.mrbIssue) { $mrb = [string]$Packet.mrbIssue }
    elseif ($Packet.mrb) { $mrb = [string]$Packet.mrb }
    $sha = ''
    if ($Packet.mergeSha) { $sha = [string]$Packet.mergeSha }
    elseif ($Packet.sha) { $sha = [string]$Packet.sha }
    Write-BobJobAuditLine -JobId ([string]$Packet.id) -Machine ([string]$Packet.machine) -Fuel ([string]$Packet.fuel) -Model ([string]$Packet.model) -Kind ([string]$Packet.kind) -PrUrl $pr -MrbIssue $mrb -Sha $sha -Status $Status
}
