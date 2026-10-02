# Dot-source only. Hidden python start for irc_agent / irc_listen.
# CreateNoWindow + UseShellExecute false. Not Start-Process -WindowStyle Hidden
# (that path raised python 0xc0000142 when Watch spawned many consoles).
# No secrets are logged.

function ConvertTo-WindowsArgumentLine {
    param([string[]]$ArgumentList)
    $parts = foreach ($raw in $ArgumentList) {
        $a = [string]$raw
        if (-not $a) { '""'; continue }
        if ($a -notmatch '[\s"]') { $a; continue }
        '"' + ($a -replace '"', '\"') + '"'
    }
    return ($parts -join ' ')
}

function Start-HiddenPython {
    param(
        [Parameter(Mandatory = $true)][string]$Python,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList,
        [string]$WorkingDirectory = ''
    )
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Python
    $psi.Arguments = (ConvertTo-WindowsArgumentLine -ArgumentList $ArgumentList)
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.ErrorDialog = $false
    if ($WorkingDirectory) {
        $psi.WorkingDirectory = $WorkingDirectory
    }
    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    if (-not $proc.Start()) {
        throw "Start-HiddenPython failed"
    }
    return [int]$proc.Id
}

function Invoke-PriorIrcClean {
    param(
        [Parameter(Mandatory = $true)][string]$Python,
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [Parameter(Mandatory = $true)][string]$Nick,
        [Parameter(Mandatory = $true)][string]$Home,
        [int]$KeepPid = 0
    )
    if (-not (Test-Path -LiteralPath $ScriptPath)) {
        throw "missing prior_irc.py at $ScriptPath"
    }
    $argList = @($ScriptPath, '--nick', $Nick, '--home', $Home)
    if ($KeepPid -gt 0) {
        $argList += @('--keep-pid', "$KeepPid")
    }
    & $Python @argList
    if ($LASTEXITCODE -ne 0) {
        throw "prior_irc.py failed exit=$LASTEXITCODE"
    }
}
