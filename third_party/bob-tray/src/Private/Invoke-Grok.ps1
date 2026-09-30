function Invoke-Grok {
    param(
        [Parameter(Mandatory)][string[]]$Args,
        [string]$WorkingDirectory,
        [int]$TimeoutSec = 180
    )

    $exe = Get-GrokExe
    if (-not $exe) {
        throw "grok missing: set BOB_GROK_EXE or install grok on PATH"
    }

    if (-not $WorkingDirectory) { $WorkingDirectory = (Get-Location).Path }
    if (-not (Test-Path $WorkingDirectory)) {
        New-Item -ItemType Directory -Force -Path $WorkingDirectory | Out-Null
    }

    $outDir = Join-Path ([IO.Path]::GetTempPath()) ('bob-grok-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    $stdoutPath = Join-Path $outDir 'stdout.txt'
    $stderrPath = Join-Path $outDir 'stderr.txt'

    $fileName = $exe
    $argList = @($Args)
    if ($exe -match '\.ps1$') {
        $fileName = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
        if (-not (Test-Path $fileName)) {
            $fileName = (Get-Command powershell.exe).Source
        }
        $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $exe) + @($Args)
    }

    $argvForLog = @($exe) + @($Args)
    $quoted = @($argList | ForEach-Object {
        '"' + (([string]$_) -replace '\\', '\\' -replace '"', '\"') + '"'
    }) -join ' '
    $prevUpdater = $env:GROK_DISABLE_AUTOUPDATER
    $env:GROK_DISABLE_AUTOUPDATER = '1'

    $sw = [Diagnostics.Stopwatch]::StartNew()
    try {
        $proc = Start-Process -FilePath $fileName -ArgumentList $quoted -WorkingDirectory $WorkingDirectory -PassThru -NoNewWindow -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
        $exited = $proc.WaitForExit($TimeoutSec * 1000)
        if (-not $exited) {
            try { Stop-ProcessTree -ProcessId $proc.Id } catch { }
            $sw.Stop()
            return [pscustomobject]@{
                ExitCode   = 124
                Stdout     = ''
                Stderr     = "timeout after ${TimeoutSec}s"
                Argv       = $argvForLog
                DurationMs = [int]$sw.ElapsedMilliseconds
                TimedOut   = $true
            }
        }
        $proc.WaitForExit()
        $sw.Stop()
        $stdout = ''
        $stderr = ''
        Start-Sleep -Milliseconds 50
        if (Test-Path $stdoutPath) { $stdout = [IO.File]::ReadAllText($stdoutPath) }
        if (Test-Path $stderrPath) { $stderr = [IO.File]::ReadAllText($stderrPath) }
        $code = 0
        try { $code = [int]$proc.ExitCode } catch { $code = 0 }
        return [pscustomobject]@{
            ExitCode   = $code
            Stdout     = $stdout
            Stderr     = $stderr
            Argv       = $argvForLog
            DurationMs = [int]$sw.ElapsedMilliseconds
            TimedOut   = $false
        }
    }
    finally {
        if ($null -eq $prevUpdater) { Remove-Item Env:GROK_DISABLE_AUTOUPDATER -ErrorAction SilentlyContinue }
        else { $env:GROK_DISABLE_AUTOUPDATER = $prevUpdater }
    }
}

function Stop-ProcessTree {
    param([int]$ProcessId)
    try {
        Get-CimInstance Win32_Process -Filter "ParentProcessId=$ProcessId" -ErrorAction SilentlyContinue | ForEach-Object {
            Stop-ProcessTree -ProcessId $_.ProcessId
        }
    }
    catch { }
    try { Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue } catch { }
}

function Get-BobArgv {
    param(
        [Parameter(Mandatory)][string]$Prompt,
        [Parameter(Mandatory)][string]$Cwd,
        [string]$SessionId,
        [switch]$Resume,
        $Profile,
        [string]$Model
    )
    $argv = New-Object System.Collections.Generic.List[string]
    [void]$argv.Add('--no-auto-update')
    [void]$argv.Add('--no-alt-screen')
    [void]$argv.Add('--output-format')
    [void]$argv.Add('json')
    [void]$argv.Add('--cwd')
    [void]$argv.Add($Cwd)
    if ($Model) {
        $cli = $Model
        try { $cli = Resolve-BobGrokCliModel -Wanted $Model } catch { }
        if ($cli) {
            [void]$argv.Add('-m')
            [void]$argv.Add($cli)
        }
    }
    if ($Resume) {
        [void]$argv.Add('-r')
        [void]$argv.Add($SessionId)
    }
    else {
        [void]$argv.Add('-s')
        [void]$argv.Add($SessionId)
    }
    $skillHint = $null
    try { $skillHint = Get-BobProjectSkillsHint } catch { }
    $rules = $null
    if ($Profile -and -not $Profile.Yolo -and $Profile.Rules) {
        $rules = ([string]$Profile.Rules).Trim()
        if ($skillHint -and $rules -notmatch 'SimonBarnett/agentic_build') {
            $rules = $rules + ' ' + $skillHint
        }
    }
    elseif ($skillHint) {
        $rules = $skillHint
    }
    if ($rules) {
        [void]$argv.Add('--rules')
        [void]$argv.Add($rules)
    }
    if ($Profile -and $Profile.Yolo) {
        [void]$argv.Add('--yolo')
    }
    [void]$argv.Add('-p')
    [void]$argv.Add($Prompt)
    return , @($argv.ToArray())
}

function Get-BobRepoPairArgv {
    param(
        [Parameter(Mandatory)][string]$Prompt,
        [Parameter(Mandatory)][string]$Cwd,
        [string]$SessionId,
        $Profile,
        [string]$Model,
        [ValidateSet('dev', 'mrb')][string]$Role
    )
    $argv = New-Object System.Collections.Generic.List[string]
    [void]$argv.Add('--no-auto-update')
    [void]$argv.Add('--no-alt-screen')
    [void]$argv.Add('--output-format')
    [void]$argv.Add('json')
    [void]$argv.Add('--cwd')
    [void]$argv.Add($Cwd)
    if ($Model) {
        $cli = $Model
        try { $cli = Resolve-BobGrokCliModel -Wanted $Model } catch { }
        if ($cli) {
            [void]$argv.Add('-m')
            [void]$argv.Add($cli)
        }
    }
    if ($SessionId) {
        [void]$argv.Add('-s')
        [void]$argv.Add($SessionId)
    }
    $skillHint = $null
    try { $skillHint = Get-BobProjectSkillsHint } catch { }
    $rules = Get-BobRepoPairRulesText -Role $Role
    if ($Profile -and -not $Profile.Yolo -and $Profile.Rules) {
        $pr = ([string]$Profile.Rules).Trim()
        if ($pr) { $rules = ($rules + ' ' + $pr).Trim() }
    }
    if ($skillHint -and $rules -notmatch 'SimonBarnett/agentic_build') {
        $rules = ($rules + ' ' + $skillHint).Trim()
    }
    if ($rules) {
        [void]$argv.Add('--rules')
        [void]$argv.Add($rules)
    }
    if ($Profile -and $Profile.Yolo) {
        [void]$argv.Add('--yolo')
    }
    if ($Profile -and $Profile.AlwaysApprove) {
        [void]$argv.Add('--always-approve')
    }
    # Interactive session (no -p/--single): grok stays running until idle-stop.
    [void]$argv.Add($Prompt)
    return @($argv.ToArray())
}
