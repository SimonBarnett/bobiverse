function Get-BobCursorAgentExePath {
    foreach ($c in @(
            (Join-Path $env:USERPROFILE '.local\bin\cursor-agent.exe'),
            (Join-Path $env:USERPROFILE '.local\bin\agent.exe'),
            (Join-Path $env:USERPROFILE '.cursor\bin\cursor-agent.exe'),
            (Join-Path $env:USERPROFILE '.cursor\bin\agent.exe'),
            (Join-Path $env:LOCALAPPDATA 'cursor-agent\cursor-agent.cmd'),
            (Join-Path $env:LOCALAPPDATA 'cursor-agent\cursor-agent.ps1'),
            (Join-Path $env:LOCALAPPDATA 'cursor-agent\cursor-agent.exe'),
            (Join-Path $env:LOCALAPPDATA 'cursor-agent\agent.cmd')
        )) {
        if ($c -and (Test-Path $c)) {
            $grok = Join-Path $env:USERPROFILE '.grok\bin\grok.exe'
            if ((Test-Path $grok) -and ((Get-Item $c).Length -eq (Get-Item $grok).Length)) { continue }
            return $c
        }
    }
    foreach ($name in @('cursor-agent.cmd', 'cursor-agent.exe', 'cursor-agent')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

function Invoke-BobCursorModelsOneShot {
    param(
        [Parameter(Mandatory)][string]$Prompt,
        [Parameter(Mandatory)][string]$Cwd,
        [string]$Model,
        [int]$TimeoutSec = 600
    )
    $fixtureText = [string]$env:BOB_GROK_TALK_CURSOR_FIXTURE
    $useFixture = ($fixtureText.Length -gt 0)
    if (-not $useFixture) {
        if ((Get-Command Test-BobUsesFakeGrok -ErrorAction SilentlyContinue) -and (Test-BobUsesFakeGrok)) {
            return $null
        }
        if ($env:BOB_NO_AGENT_LAUNCH -match '^(?i)(1|true|yes)$') { return $null }
    }
    if (-not $Model) { $Model = Get-BobJobModel -Kind build -Fuel cursor-models }

    $utf8 = New-Object System.Text.UTF8Encoding $false
    $jobId = [guid]::NewGuid().ToString('N')
    $logDir = Join-Path $env:TEMP ('bob-cursor-oneshot-' + $jobId)
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $logPath = Join-Path $logDir 'out.txt'
    $errPath = Join-Path $logDir 'err.txt'

    if ($useFixture) {
        $promptFile = Join-Path $logDir 'prompt.txt'
        [IO.File]::WriteAllText($promptFile, $Prompt, $utf8)
        $fixtureFile = Join-Path $logDir 'fixture.txt'
        [IO.File]::WriteAllText($fixtureFile, $fixtureText, $utf8)
        $launch = Join-Path $logDir 'launch.ps1'
        $launchBody = @"
`$ErrorActionPreference = 'Stop'
`$out = '$($logPath.Replace("'","''"))'
`$text = [IO.File]::ReadAllText('$($fixtureFile.Replace("'","''"))')
[IO.File]::WriteAllText(`$out, `$text, (New-Object System.Text.UTF8Encoding `$false))
"@
        [IO.File]::WriteAllText($launch, $launchBody, $utf8)
    }
    else {
        $agent = Get-BobCursorAgentExePath
        if (-not $agent) { return $null }

        $stExe = $agent
        $stArg = @('status')
        if ($agent -match '\.cmd$' -or $agent -match '\.ps1$') {
            $stExe = (Get-Command powershell.exe).Source
            $ps1Status = $agent
            if ($agent -match '\.cmd$') { $ps1Status = Join-Path (Split-Path $agent) 'cursor-agent.ps1' }
            $stArg = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $ps1Status, 'status')
        }
        $savedEap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $st = & $stExe @stArg 2>$null | Out-String
        }
        catch {
            $st = [string]$_
        }
        finally {
            $ErrorActionPreference = $savedEap
        }
        if ($st -match '(?i)not logged in') { return $null }

        $promptFile = Join-Path $logDir 'prompt.txt'
        [IO.File]::WriteAllText($promptFile, $Prompt, $utf8)
        $ps1 = $agent
        if ($agent -match '\.cmd$') { $ps1 = Join-Path (Split-Path $agent) 'cursor-agent.ps1' }
        $launch = Join-Path $logDir 'launch.ps1'
        $launchBody = @"
`$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath '$($Cwd.Replace("'","''"))'
`$prompt = [IO.File]::ReadAllText('$($promptFile.Replace("'","''"))')
& '$($ps1.Replace("'","''"))' -p --force --trust --output-format text --model '$($Model.Replace("'","''"))' -- `$prompt 1>'$($logPath.Replace("'","''"))' 2>'$($errPath.Replace("'","''"))'
"@
        [IO.File]::WriteAllText($launch, $launchBody, $utf8)
    }

    $exe = (Get-Command powershell.exe).Source
    $cmdLine = '"{0}" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{1}"' -f $exe, $launch
    $created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
        CommandLine      = $cmdLine
        CurrentDirectory = $Cwd
    }
    if ($created.ReturnValue -ne 0 -or -not $created.ProcessId) { return $null }
    $procId = [int]$created.ProcessId
    $deadline = [datetime]::UtcNow.AddSeconds($TimeoutSec)
    while ([datetime]::UtcNow -lt $deadline) {
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if (-not $proc) { break }
        Start-Sleep -Seconds 2
    }
    $still = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($still) {
        try { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue } catch { }
    }
    if (Test-Path $logPath) {
        $raw = Get-Content -LiteralPath $logPath -Raw -ErrorAction SilentlyContinue
        if ($raw -and $raw.Trim()) { return [string]$raw.Trim() }
    }
    return $null
}
