# FR #8698 / BOB-52: Priority no-token dialog + quit (do not start without tokens).

function Invoke-BobPriorityNoTokenGate {
    [CmdletBinding()]
    param(
        [string]$FixturePath,
        [Nullable[int]]$Remaining,
        [string]$LogPath,
        [switch]$NoUi,
        [switch]$Quiet
    )
    $exhausted = Test-BobPriorityFuelExhausted -FixturePath $FixturePath -Remaining $Remaining
    if (-not $LogPath) {
        $override = [string]$env:BOB_PRIORITY_NOTOKEN_LOG
        if ($override -and $override.Trim().Length -gt 0) {
            $LogPath = $override.Trim()
        }
        else {
            $base = Join-Path $env:LOCALAPPDATA 'Bobiverse\logs'
            if (-not (Test-Path -LiteralPath $base)) {
                New-Item -ItemType Directory -Force -Path $base | Out-Null
            }
            $LogPath = Join-Path $base 'priority-no-token-gate.log'
        }
    }
    $parent = Split-Path -Parent $LogPath
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $ts = (Get-Date).ToUniversalTime().ToString('o')
    if (-not $exhausted) {
        $lines = @(
            "ts=$ts",
            'fr=8698',
            'bob=BOB-52',
            'agent=priority',
            'gate=allow',
            'dialog=none',
            'quit=false',
            'start=allowed'
        )
        $text = ($lines -join [Environment]::NewLine) + [Environment]::NewLine
        [IO.File]::WriteAllText($LogPath, $text, (New-Object System.Text.UTF8Encoding $false))
        if (-not $Quiet) { Write-Output $text.TrimEnd() }
        return [pscustomobject]@{
            AllowStart = $true
            Quit       = $false
            Dialog     = 'none'
            Reason     = 'fuel-ok'
            LogPath    = $LogPath
        }
    }

    $ui = -not $NoUi
    if ($env:BOB_TRAY_NO_UI -match '^(?i)(1|true|yes)$') { $ui = $false }
    if ($ui) {
        try {
            Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue | Out-Null
            [void][System.Windows.Forms.MessageBox]::Show(
                'no tokens',
                'Priority seat',
                [System.Windows.Forms.MessageBoxButtons]::OK,
                [System.Windows.Forms.MessageBoxIcon]::Information
            )
        }
        catch { }
    }
    $lines = @(
        "ts=$ts",
        'fr=8698',
        'bob=BOB-52',
        'agent=priority',
        'gate=refuse',
        'dialog=no-tokens',
        'quit=true',
        'start=blocked',
        'reason=fuel-empty'
    )
    $text = ($lines -join [Environment]::NewLine) + [Environment]::NewLine
    [IO.File]::WriteAllText($LogPath, $text, (New-Object System.Text.UTF8Encoding $false))
    if (-not $Quiet) { Write-Output $text.TrimEnd() }
    return [pscustomobject]@{
        AllowStart = $false
        Quit       = $true
        Dialog     = 'no-tokens'
        Reason     = 'fuel-empty'
        LogPath    = $LogPath
    }
}

function Start-BobTrayPriorityAgent {
    [CmdletBinding()]
    param(
        [string]$FixturePath,
        [Nullable[int]]$Remaining,
        [string]$LogPath,
        [switch]$NoUi
    )
    $gate = Invoke-BobPriorityNoTokenGate -FixturePath $FixturePath -Remaining $Remaining -LogPath $LogPath -NoUi:$NoUi -Quiet
    if (-not $gate.AllowStart) {
        return [pscustomobject]@{
            Started    = $false
            Quit       = $true
            AllowStart = $false
            Reason     = $gate.Reason
            LogPath    = $gate.LogPath
        }
    }
    # BOB-50 owns PriorityAgent.exe process start; this slice only gates.
    return [pscustomobject]@{
        Started    = $false
        Quit       = $false
        AllowStart = $true
        Reason     = 'gate-allow-await-bob-50-start'
        LogPath    = $gate.LogPath
        Gated      = $true
    }
}