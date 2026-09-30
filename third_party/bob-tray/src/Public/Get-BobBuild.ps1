function Get-BobBuild {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$JobId
    )
    $job = Read-FleetJob -JobId $JobId
    if (-not $job) {
        throw "No fleet job $JobId"
    }
    return $job
}

function Get-BobBuilds {
    [CmdletBinding()]
    param(
        [string]$Machine,
        [ValidateSet('inbox', 'running', 'outbox')][string]$Lane
    )
    $root = Initialize-FleetRoot
    $lanes = @('inbox', 'running', 'outbox')
    if ($Lane) { $lanes = @($Lane) }
    $rows = @()
    foreach ($ln in $lanes) {
        $dir = Join-Path $root $ln
        if ($Machine) {
            $dir = Join-Path $dir (ConvertTo-MachineId $Machine)
        }
        if (-not (Test-Path $dir)) { continue }
        foreach ($f in @(Get-ChildItem $dir -Recurse -Filter '*.json' -ErrorAction SilentlyContinue)) {
            $j = Read-JsonFile $f.FullName
            if ($j) {
                $j | Add-Member -NotePropertyName lane -NotePropertyValue $ln -Force
                $rows += $j
            }
        }
    }
    return $rows
}
