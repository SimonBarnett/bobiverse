function Get-BobResult {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$SessionId
    )
    $dir = Get-WorkerDir $SessionId
    $path = Join-Path $dir 'last_result.json'
    $r = Read-JsonFile $path
    if (-not $r) {
        throw "No last_result for session $SessionId"
    }
    return $r
}
