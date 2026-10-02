function Register-BobMachine {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Id,
        [string[]]$CwdRoots,
        [string[]]$Profiles = @('formprep', 'teams', 'mud', 'generic'),
        [string]$Kind = 'windows'
    )
    $mid = ConvertTo-MachineId $Id
    Initialize-BridgeRoot | Out-Null

    $roots = @()
    foreach ($r in @($CwdRoots)) {
        if (-not $r) { continue }
        $s = [string]$r.Trim()
        if ($s -match '^[A-Za-z]:$') { $s = $s + '\' }
        try { $s = [IO.Path]::GetFullPath($s) } catch { }
        if ($s -match '^[A-Za-z]:\\?$') {
            # Keep drive-root form ending with backslash for StartsWith checks
            $s = $s.Substring(0, 2) + '\'
        }
        $roots += $s
    }

    $kindVal = 'windows'
    if ($Kind) { $kindVal = $Kind.Trim().ToLowerInvariant() }
    $record = [pscustomobject]@{
        id           = $mid
        hostname     = $env:COMPUTERNAME
        windowsUser  = "$env:USERDOMAIN\$env:USERNAME"
        mssql        = 'integrated'
        grokBot      = $true
        cwdRoots     = @($roots)
        profiles     = @($Profiles)
        kind         = $kindVal
        lastSeen     = [DateTime]::UtcNow.ToString('o')
    }
    $record = Update-BobMachineGhPostingSnapshot -Record $record
    Write-JsonFile (Join-Path (Get-BridgeRoot) 'machine.json') $record
    $dir = Join-Path (Initialize-FleetRoot) 'machines'
    Write-JsonFile (Join-Path $dir ($mid + '.json')) $record
    $env:BOB_MACHINE_ID = $mid
    try { Write-BobFleetPeekSnapshot } catch { }
    return $record
}
