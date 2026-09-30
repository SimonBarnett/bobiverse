function Get-BobStatus {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$SessionId
    )
    $path = Join-Path (Get-WorkerDir $SessionId) 'status.json'
    $s = Read-JsonFile $path
    if (-not $s) {
        throw "No status for session $SessionId"
    }
    return $s
}
