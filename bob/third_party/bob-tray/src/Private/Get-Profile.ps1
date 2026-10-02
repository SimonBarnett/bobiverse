function Get-Profile {
    param(
        [string]$Name = 'generic'
    )
    if (-not $Name) { $Name = 'generic' }
    $root = Initialize-BridgeRoot
    $cfgPath = Join-Path $root 'config.json'
    $cfg = Read-JsonFile $cfgPath
    if (-not $cfg) {
        $bundled = Join-Path (Get-ModuleRoot) 'config\default.json'
        $cfg = Read-JsonFile $bundled
    }
    $profiles = $cfg.profiles
    $p = $null
    if ($profiles) {
        $p = $profiles.$Name
        if (-not $p) {
            foreach ($prop in $profiles.PSObject.Properties) {
                if ($prop.Name -eq $Name) { $p = $prop.Value; break }
            }
        }
    }
    if (-not $p) {
        throw "Unknown profile '$Name'. Known: formprep, teams, mud, generic."
    }
    # 0 (or absent) = no per-machine worker cap
    $maxMachine = 0
    $prop = $cfg.PSObject.Properties['max_workers_per_machine']
    if ($prop) { $maxMachine = [int]$prop.Value }
    return [pscustomobject]@{
        Name                   = $Name
        Yolo                   = [bool]$p.yolo
        TimeoutSec             = [int]$p.timeoutSec
        MaxPerCwd              = [int]$p.maxPerCwd
        Rules                  = [string]$p.rules
        MaxWorkersPerMachine   = $maxMachine
    }
}
