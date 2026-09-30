function Get-BobMachines {
    [CmdletBinding()]
    param()
    $dir = Join-Path (Initialize-FleetRoot) 'machines'
    $rows = @()
    foreach ($f in @(Get-ChildItem $dir -Filter '*.json' -ErrorAction SilentlyContinue)) {
        $m = Read-JsonFile $f.FullName
        if ($m) { $rows += $m }
    }
    return $rows
}
