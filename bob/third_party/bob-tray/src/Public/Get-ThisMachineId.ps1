function Get-ThisMachineId {
    if ($env:BOB_MACHINE_ID -and $env:BOB_MACHINE_ID.Trim()) {
        return $env:BOB_MACHINE_ID.Trim().ToLowerInvariant()
    }
    $path = Join-Path (Get-BridgeRoot) 'machine.json'
    $m = Read-JsonFile $path
    if ($m -and $m.id) { return ([string]$m.id).ToLowerInvariant() }
    return $null
}
