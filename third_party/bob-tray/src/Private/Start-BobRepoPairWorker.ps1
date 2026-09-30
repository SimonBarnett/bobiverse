function Get-BobRepoPairRulesText {
    param([Parameter(Mandatory)][ValidateSet('dev', 'mrb')][string]$Role)
    $skillList = if ($Role -eq 'dev') {
        'bob-spec-intake, bob-build-dispatch, grok-build-fleet, bob-irc, reinstall-agentic-build-skills'
    }
    else {
        'bob-hostile-mrb, bob-irc, reinstall-agentic-build-skills'
    }
    return @(
        "Persistent repo-pair $Role seat. Load skills: $skillList."
        'JOIN the machine shop channel only (never #bobiverse).'
        'Do your own implement or hostile MRB work in this seat.'
        'Do not invoke Start-BobBuild, Start-BobBuildLoop, Start-BobMrbHandoff, or cursor-mrb-dev handoff.'
        'Chair assigns work via inbox/chair-task; execute assigned tasks only.'
        'POST working_on via Update-BobRepoWorkerWorkingOn. Never stamp ready for human UAT.'
        'MRB: merge duplicate issues, close finished/superseded issues, merge PR on PASS-nits.'
        'Workers report status via webhook only; no shop or fleet PRIVMSG.'
    ) -join ' '
}

function Get-BobRepoPairWorkerProfile {
    param([Parameter(Mandatory)][ValidateSet('dev', 'mrb')][string]$Role)
    if ($Role -eq 'dev') { return 'repo-pair-dev' }
    return 'repo-pair-mrb'
}

function Select-BobRepoPairFuel {
    param([Parameter(Mandatory)][ValidateSet('dev', 'mrb')][string]$Role)
    if (Test-BobUsesFakeGrok) { return 'grok-build' }
    $cur = 0
    try {
        $c = Get-BobCursorAgentWeeklyRemaining
        if ($c -and $null -ne $c.remaining_pct) {
            $rp = $c.remaining_pct
            if ($rp -is [System.Array]) { $rp = @($rp)[0] }
            $cur = [int]$rp
        }
    }
    catch { }
    if ($cur -gt 0) { return 'cursor-models' }
    return 'grok-build'
}

function Get-BobRepoPairTierModel {
    param(
        [Parameter(Mandatory)][ValidateSet('dev', 'mrb', 'uat')][string]$Role,
        [string]$Fuel
    )
    $bundled = Join-Path (Get-ModuleRoot) 'config\default.json'
    $cfg = $null
    try { $cfg = Read-JsonFile $bundled } catch { }
    $tier = 'medium'
    if ($Role -eq 'dev') { $tier = 'less' }
    elseif ($Role -eq 'uat') { $tier = 'more' }
    $fromTier = $null
    if ($cfg -and $cfg.repoPairModelTier -and $cfg.repoPairModelTier.$tier) {
        $fromTier = [string]$cfg.repoPairModelTier.$tier
    }
    if ($fromTier) {
        if ($Fuel -eq 'cursor-models' -and $fromTier -match '^(composer-|claude-|gpt-|cursor-|muse-)') {
            return $fromTier
        }
        if ($Fuel -ne 'cursor-models' -and $fromTier -match '^grok-') {
            return $fromTier
        }
        if ($Fuel -eq 'cursor-models') { return Get-BobJobModel -Kind $(if ($Role -eq 'mrb') { 'mrb' } else { 'build' }) -Fuel cursor-models }
        return Get-BobJobModel -Kind $(if ($Role -eq 'mrb') { 'mrb' } else { 'build' }) -Fuel grok-build
    }
    return Get-BobJobModel -Kind $(if ($Role -eq 'mrb') { 'mrb' } else { 'build' }) -Fuel $Fuel
}

function Select-BobRepoPairInvokeMode {
    param(
        [Parameter(Mandatory)][ValidateSet('dev', 'mrb')][string]$Role,
        [string]$Fuel
    )
    $hostPref = $null
    if ($env:BOB_REPO_PAIR_AGENT_HOST -and $env:BOB_REPO_PAIR_AGENT_HOST.Trim()) {
        $hostPref = $env:BOB_REPO_PAIR_AGENT_HOST.Trim().ToLowerInvariant()
    }
    if ($hostPref -eq 'agent.com' -and (Test-GrokBotAvailable)) {
        return 'grokbot'
    }
    if ($Fuel -eq 'cursor-models') {
        if (Get-BobCursorAgentExePath) { return 'cursor-cli' }
    }
    if (Get-GrokExe) { return 'grok-cli' }
    if (Get-BobCursorAgentExePath) { return 'cursor-cli' }
    return 'grok-cli'
}

function Get-BobRepoPairGrokBotAgent {
    if ($env:BOB_REPO_PAIR_GROK_BOT_AGENT -and $env:BOB_REPO_PAIR_GROK_BOT_AGENT.Trim()) {
        return $env:BOB_REPO_PAIR_GROK_BOT_AGENT.Trim()
    }
    $mid = $null
    try { $mid = Get-ThisMachineId } catch { }
    if ($mid) { return ($mid + '-builder') }
    return 'Bob'
}

function Get-BobRepoPairWorkerModel {
    param(
        [Parameter(Mandatory)][ValidateSet('dev', 'mrb')][string]$Role,
        [string]$Fuel,
        [string]$InvokeMode
    )
    if ($InvokeMode -eq 'grokbot') {
        return Get-BobRepoPairTierModel -Role $Role -Fuel grok-build
    }
    $fuelUse = if ($InvokeMode -eq 'cursor-cli') { 'cursor-models' } else { 'grok-build' }
    return Get-BobRepoPairTierModel -Role $Role -Fuel $fuelUse
}

function ConvertTo-BobRepoPairProcessId {
    param($Raw)
    if ($null -eq $Raw) { return $null }
    if ($Raw -is [System.Array]) { $Raw = @($Raw)[0] }
    try { return [int]$Raw } catch { return $null }
}

function Normalize-BobRepoPairArgvList {
    param($Argv)
    $list = @($Argv)
    if ($list.Count -eq 1 -and ($list[0] -is [System.Array])) {
        $list = @($list[0])
    }
    return @($list | ForEach-Object { [string]$_ })
}

function Get-BobRepoPairIrcAgentScriptPath {
    $ircRoot = $null
    if (Test-Path 'C:\ai\agentic_irc') { $ircRoot = 'C:\ai\agentic_irc' }
    elseif (Test-Path 'D:\ai\agentic_irc') { $ircRoot = 'D:\ai\agentic_irc' }
    if ($ircRoot) {
        $agent = Join-Path $ircRoot 'scripts\irc_agent.py'
        if (Test-Path $agent) { return $agent }
    }
    return $null
}

function Start-BobRepoPairShopIrc {
    param(
        [Parameter(Mandatory)][string]$ShopChannel,
        [Parameter(Mandatory)][string]$ShopNick,
        [Parameter(Mandatory)][string]$SessionId
    )
    $home = Get-BobIrcHome
    if (-not $home) {
        return [pscustomobject]@{ ok = $false; error = 'no_irc_home' }
    }
    New-Item -ItemType Directory -Force -Path $home | Out-Null
    $manifestPath = Join-Path $home ('shop-join-' + $SessionId + '.json')
    $ircPid = $null
    $joinKind = 'irc_agent'

    if (Test-BobUsesFakeGrok -ErrorAction SilentlyContinue) {
        return [pscustomobject]@{ ok = $false; error = 'integrated_shop_join'; reason = 'worker agent joins shop' }
    }
    $agent = Get-BobRepoPairIrcAgentScriptPath
        if (-not $agent) {
            return [pscustomobject]@{ ok = $false; error = 'no_irc_agent' }
        }
        $py = $null
        foreach ($c in @(
                (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
                (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe')
            )) {
            if (Test-Path $c) { $py = $c; break }
        }
        if (-not $py) {
            $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
            if ($cmd -and $cmd.Source -notmatch 'WindowsApps') { $py = $cmd.Source }
        }
        if (-not $py) {
            return [pscustomobject]@{ ok = $false; error = 'no_python' }
        }
        $cfg = $null
        try { $cfg = Get-BobiverseConfig } catch { }
        $ircHost = '127.0.0.1'
        $ircPort = 6697
        if ($cfg -and $cfg.host -and [string]$cfg.host -ne 'irc.libera.chat') {
            $ircHost = [string]$cfg.host
            if ($cfg.port) { $ircPort = [int]$cfg.port }
        }
        if ($env:BOB_IRC_HOST -and $env:BOB_IRC_HOST.Trim()) {
            $ircHost = $env:BOB_IRC_HOST.Trim()
        }
        $pwFile = Join-Path $env:USERPROFILE '.grok\ergo\connect.password'
        if (-not (Test-Path $pwFile)) {
            return [pscustomobject]@{ ok = $false; error = 'no_irc_password' }
        }
        $env:AGENTIC_IRC_PASSWORD = (Get-Content $pwFile -Raw).Trim()
        $env:AGENTIC_IRC_HOME = $home
        $argList = @(
            '-u', $agent,
            '--host', $ircHost,
            '--port', "$ircPort",
            '--nick', $ShopNick,
            '--channel', $ShopChannel,
            '--home', $home
        )
        $quoted = @($argList | ForEach-Object {
            '"' + (([string]$_) -replace '"', '\"') + '"'
        }) -join ' '
        $cmdLine = '"{0}" {1}' -f $py, $quoted
        $ircRoot = Split-Path (Split-Path $agent -Parent) -Parent
        $created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
            CommandLine      = $cmdLine
            CurrentDirectory = $ircRoot
        }
        if ($created.ReturnValue -ne 0 -or -not $created.ProcessId) {
            return [pscustomobject]@{ ok = $false; error = 'irc_spawn_failed' }
        }
    $ircPid = ConvertTo-BobRepoPairProcessId $created.ProcessId
    $joinKind = 'irc_agent'

    if (-not $ircPid) {
        return [pscustomobject]@{ ok = $false; error = 'irc_join_failed' }
    }

    $manifest = [pscustomobject]@{
        channel       = $ShopChannel
        nick          = $ShopNick
        sessionId     = $SessionId
        joinedAt      = [DateTime]::UtcNow.ToString('o')
        policy        = 'shop_only_no_bobiverse'
        joinKind      = $joinKind
        shopNickLive  = $true
        ircAgentPid   = $ircPid
    }
    Write-JsonFile $manifestPath $manifest
    return [pscustomobject]@{
        ok          = $true
        nick        = $ShopNick
        channel     = $ShopChannel
        manifest    = $manifestPath
        pid         = $ircPid
        joinKind    = $joinKind
    }
}

function Start-BobRepoPairSeatAgent {
    param(
        [Parameter(Mandatory)][ValidateSet('dev', 'mrb')][string]$Role,
        [Parameter(Mandatory)][string]$Cwd,
        [Parameter(Mandatory)][string]$SessionId,
        [Parameter(Mandatory)][string]$Prompt,
        [Parameter(Mandatory)][string]$InvokeMode,
        [string]$Model,
        $Profile,
        [string[]]$Argv,
        [string]$ShopNick,
        [string]$ShopChannel
    )
    $dir = Get-WorkerDir $SessionId
    $heartbeatPath = Join-Path $dir 'heartbeat.json'
    $agentPath = Join-Path $dir 'seat-agent.ps1'
    $moduleRoot = Get-ModuleRoot
    $psd1 = Join-Path $moduleRoot 'src\BobBridge.psd1'
    $grokExe = Get-GrokExe
    if (-not $grokExe) { $grokExe = '' }
    $ircHome = Get-BobIrcHome
    $shopManifest = ''
    if ($ircHome) { $shopManifest = Join-Path $ircHome ('shop-join-' + $SessionId + '.json') }
    $argvFlat = Normalize-BobRepoPairArgvList -Argv $Argv
    $argvJsonPath = Join-Path $dir 'outbox\argv.json'
    Write-JsonFile $argvJsonPath $argvFlat
    $grokLaunch = Join-Path $dir 'seat-grok.launch.ps1'
    $grokSessionId = $SessionId
    if ($InvokeMode -eq 'grok-cli' -and $grokExe) {
        $grokLaunchBody = @"
`$ErrorActionPreference = 'SilentlyContinue'
`$env:BOB_REPO_PAIR_HEARTBEAT_PATH = '$($heartbeatPath.Replace("'","''"))'
`$env:BOB_REPO_PAIR_WORKER_DIR = '$($dir.Replace("'","''"))'
`$env:BOB_REPO_PAIR_ROLE = '$Role'
`$env:BOB_REPO_PAIR_SHOP_NICK = '$($ShopNick.Replace("'","''"))'
`$env:BOB_REPO_PAIR_SHOP_CHANNEL = '$($ShopChannel.Replace("'","''"))'
`$env:BOB_REPO_PAIR_SHOP_MANIFEST_PATH = '$($shopManifest.Replace("'","''"))'
`$parsed = Get-Content -LiteralPath '$($argvJsonPath.Replace("'","''"))' -Raw | ConvertFrom-Json
`$argvRaw = @(`$parsed | ForEach-Object { [string]`$_ })
`$grok = '$($grokExe.Replace("'","''"))'
`$sessionId = '$($grokSessionId.Replace("'","''"))'
`$workerDir = '$($dir.Replace("'","''"))'
`$lastChair = `$null
`$agentPid = `$null
function Start-GrokSeatProcess {
    param([string[]]`$Argv)
    if (`$grok -match '\.ps1`$') {
        `$argList = @('-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',`$grok) + `$Argv
        return Start-Process -FilePath (Get-Command powershell.exe).Source -ArgumentList `$argList -WorkingDirectory '$($cwdFull.Replace("'","''"))' -PassThru
    }
    return Start-Process -FilePath `$grok -ArgumentList `$Argv -WorkingDirectory '$($cwdFull.Replace("'","''"))' -WindowStyle Hidden -PassThru
}
`$cp = Start-GrokSeatProcess -Argv `$argvRaw
`$agentPid = `$cp.Id
while (`$true) {
    if (`$agentPid) {
        `$live = Get-Process -Id `$agentPid -ErrorAction SilentlyContinue
        if (-not `$live) { break }
        @{ seat = '$Role'; sessionId = '$SessionId'; at = [DateTime]::UtcNow.ToString('o'); agentPid = `$agentPid } | ConvertTo-Json -Compress | Set-Content -LiteralPath '$($heartbeatPath.Replace("'","''"))' -Encoding utf8
    }
    `$inbox = Join-Path `$workerDir 'inbox\chair-task.txt'
    if (Test-Path -LiteralPath `$inbox) {
        try {
            `$chair = ([IO.File]::ReadAllText(`$inbox)).Trim()
            if (`$chair -and `$chair -ne `$lastChair) {
                `$lastChair = `$chair
                `$touch = Join-Path `$workerDir 'inbox\chair-touched.txt'
                [IO.File]::WriteAllText(`$touch, `$chair)
                `$turn = @('--no-auto-update','--no-alt-screen','--output-format','json','-r',`$sessionId,'-p',`$chair)
                `$tp = Start-GrokSeatProcess -Argv `$turn
                while (`$tp -and (Get-Process -Id `$tp.Id -ErrorAction SilentlyContinue)) { Start-Sleep -Seconds 2 }
            }
        }
        catch { }
    }
    if ('$Role' -eq 'mrb') {
        try {
            Import-Module '$($psd1.Replace("'","''"))' -Force -ErrorAction SilentlyContinue
            Invoke-BobRepoPairMrbSeatHygiene -Seat '$Role' -WorkerDir `$workerDir | Out-Null
        }
        catch { }
    }
    Start-Sleep -Seconds 5
}
"@
        [IO.File]::WriteAllText($grokLaunch, $grokLaunchBody)
    }
    $cursorAgent = ''
    if ($InvokeMode -eq 'cursor-cli') {
        $ca = Get-BobCursorAgentExePath
        if ($ca) { $cursorAgent = $ca }
    }
    $cwdFull = [IO.Path]::GetFullPath($Cwd)
    $promptFile = Join-Path $dir 'outbox\initial-prompt.txt'
    [IO.File]::WriteAllText($promptFile, $Prompt)
    $pairRules = (Get-BobRepoPairRulesText -Role $Role).Replace("'", "''")
    if ($Profile -and $Profile.Rules) {
        $pairRules = ($pairRules + ' ' + ([string]$Profile.Rules)).Replace("'", "''")
    }
    $skillHint = ''
    try { $skillHint = (Get-BobProjectSkillsHint).Replace("'", "''") } catch { }
    if ($skillHint -and $pairRules -notmatch 'SimonBarnett/agentic_build') {
        $pairRules = ($pairRules + ' ' + $skillHint).Trim()
    }
    if ($InvokeMode -eq 'cursor-cli' -and $cursorAgent) {
        $ps1 = $cursorAgent
        if ($cursorAgent -match '\.cmd$') { $ps1 = Join-Path (Split-Path $cursorAgent) 'cursor-agent.ps1' }
        $launch = Join-Path $dir 'seat-cursor-persistent.ps1'
        $launchBody = @"
`$ErrorActionPreference = 'SilentlyContinue'
Set-Location -LiteralPath '$($cwdFull.Replace("'","''"))'
`$hb = '$($heartbeatPath.Replace("'","''"))'
`$rules = '$pairRules'
`$model = '$($Model.Replace("'","''"))'
`$ps1 = '$($ps1.Replace("'","''"))'
`$workerDir = '$($dir.Replace("'","''"))'
`$lastTask = `$null
`$cp = `$null
while (`$true) {
    `$inbox = Join-Path `$workerDir 'inbox\chair-task.txt'
    `$task = `$null
    if (Test-Path -LiteralPath `$inbox) {
        try { `$task = ([IO.File]::ReadAllText(`$inbox)).Trim() } catch { }
    }
    if (-not `$task) {
        try { `$task = ([IO.File]::ReadAllText('$($promptFile.Replace("'","''"))')).Trim() } catch { }
    }
    if (`$task -and `$task -ne `$lastTask) {
        if (`$cp) {
            try { Stop-Process -Id `$cp.Id -Force -ErrorAction SilentlyContinue } catch { }
            `$cp = `$null
        }
        `$lastTask = `$task
        `$cp = Start-Process -FilePath (Get-Command powershell.exe).Source -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',`$ps1,'persist','--force','--trust','--output-format','text','--model',`$model,'--rules',`$rules,'--',`$task) -WorkingDirectory '$($cwdFull.Replace("'","''"))' -PassThru
    }
    if (`$cp -and (Get-Process -Id `$cp.Id -ErrorAction SilentlyContinue)) {
        @{ seat = '$Role'; sessionId = '$SessionId'; at = [DateTime]::UtcNow.ToString('o'); agentPid = `$cp.Id } | ConvertTo-Json -Compress | Set-Content -LiteralPath `$hb -Encoding utf8
    }
    if ('$Role' -eq 'mrb') {
        try {
            Import-Module '$($psd1.Replace("'","''"))' -Force -ErrorAction SilentlyContinue
            Invoke-BobRepoPairMrbSeatHygiene -Seat '$Role' -WorkerDir `$workerDir | Out-Null
        }
        catch { }
    }
    Start-Sleep -Seconds 5
}
"@
        [IO.File]::WriteAllText($launch, $launchBody)
    }

    $grokBotAgent = Get-BobRepoPairGrokBotAgent
    $agentBody = @"
`$ErrorActionPreference = 'SilentlyContinue'
`$env:BOB_BRIDGE_HOME = '$((Get-BridgeRoot).Replace("'","''"))'
`$env:BOB_REPO_PAIR_INTEGRATED_IRC = '1'
`$sessionId = '$SessionId'
`$role = '$Role'
`$mode = '$InvokeMode'
`$hb = '$($heartbeatPath.Replace("'","''"))'
`$cwd = '$($cwdFull.Replace("'","''"))'
`$childPid = `$null
`$workerDir = '$($dir.Replace("'","''"))'
`$env:BOB_REPO_PAIR_HEARTBEAT_PATH = `$hb
`$env:BOB_REPO_PAIR_WORKER_DIR = `$workerDir
`$env:BOB_REPO_PAIR_ROLE = `$role
`$env:BOB_REPO_PAIR_SHOP_NICK = '$($ShopNick.Replace("'","''"))'
`$env:BOB_REPO_PAIR_SHOP_CHANNEL = '$($ShopChannel.Replace("'","''"))'
`$env:BOB_REPO_PAIR_SHOP_MANIFEST_PATH = '$($shopManifest.Replace("'","''"))'
Import-Module '$($psd1.Replace("'","''"))' -Force
if (`$env:BOB_REPO_PAIR_SHOP_CHANNEL -and `$env:BOB_REPO_PAIR_SHOP_NICK -and `$env:BOB_REPO_PAIR_SHOP_MANIFEST_PATH) {
    if (-not (Test-Path -LiteralPath `$env:BOB_REPO_PAIR_SHOP_MANIFEST_PATH)) {
        Start-BobRepoPairShopIrc -ShopChannel `$env:BOB_REPO_PAIR_SHOP_CHANNEL -ShopNick `$env:BOB_REPO_PAIR_SHOP_NICK -SessionId `$sessionId | Out-Null
    }
}

if (`$mode -eq 'grok-cli') {
    `$launch = Join-Path `$workerDir 'seat-grok.launch.ps1'
    if (Test-Path -LiteralPath `$launch) {
        `$p = Start-Process -FilePath (Get-Command powershell.exe).Source -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',`$launch) -WorkingDirectory `$cwd -PassThru
        `$childPid = `$p.Id
    }
    Import-Module '$($psd1.Replace("'","''"))' -Force
    function Sync-ChairTouch {
        `$touched = Join-Path `$workerDir 'inbox\chair-touched.txt'
        if (Test-Path -LiteralPath `$touched) {
            try {
                `$t = ([IO.File]::ReadAllText(`$touched)).Trim()
                if (`$t) { Touch-BobRepoPairSeat -Seat `$role -WorkingOn `$t | Out-Null }
            }
            catch { }
        }
    }
    while (`$true) {
        if (`$childPid) {
            `$cp = Get-Process -Id `$childPid -ErrorAction SilentlyContinue
            if (-not `$cp) { break }
        }
        Sync-ChairTouch
        Start-Sleep -Seconds 5
    }
    exit 0
}

if (`$mode -eq 'grokbot') {
    `$agentNick = '$($grokBotAgent.Replace("'","''"))'
    `$lastTask = `$null
    while (`$true) {
        `$inbox = Join-Path `$workerDir 'inbox\chair-task.txt'
        `$task = `$null
        if (Test-Path -LiteralPath `$inbox) {
            try { `$task = ([IO.File]::ReadAllText(`$inbox)).Trim() } catch { }
        }
        if (`$task -and `$task -ne `$lastTask) {
            `$lastTask = `$task
            try {
                `$run = Invoke-GrokBotApi -Action send -Agent `$agentNick -Text `$task -Wait -TimeoutSec 600
                if (`$run.Parsed -and `$run.Parsed.text) {
                    [IO.File]::WriteAllText((Join-Path `$workerDir 'outbox\last-grokbot.txt'), [string]`$run.Parsed.text)
                }
                Touch-BobRepoPairSeat -Seat `$role -WorkingOn `$task | Out-Null
            }
            catch { }
        }
        @{ seat = `$role; sessionId = `$sessionId; at = [DateTime]::UtcNow.ToString('o'); agentPid = `$PID } | ConvertTo-Json -Compress | Set-Content -LiteralPath `$hb -Encoding utf8
        if (`$role -eq 'mrb') {
            try { Invoke-BobRepoPairMrbSeatHygiene -Seat `$role -WorkerDir `$workerDir | Out-Null } catch { }
        }
        Start-Sleep -Seconds 15
    }
}

if (`$mode -eq 'cursor-cli') {
    function Sync-ChairTouch {
        `$touched = Join-Path `$workerDir 'inbox\chair-touched.txt'
        if (Test-Path -LiteralPath `$touched) {
            try {
                `$t = ([IO.File]::ReadAllText(`$touched)).Trim()
                if (`$t) { Touch-BobRepoPairSeat -Seat `$role -WorkingOn `$t | Out-Null }
            }
            catch { }
        }
    }
    `$launch = Join-Path `$workerDir 'seat-cursor-persistent.ps1'
    if (Test-Path -LiteralPath `$launch) {
        `$p = Start-Process -FilePath (Get-Command powershell.exe).Source -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',`$launch) -WorkingDirectory `$cwd -PassThru
        `$childPid = `$p.Id
    }
    while (`$true) {
        if (`$childPid) {
            `$cp = Get-Process -Id `$childPid -ErrorAction SilentlyContinue
            if (-not `$cp) { break }
        }
        Sync-ChairTouch
        Start-Sleep -Seconds 5
    }
    exit 0
}

exit 2
"@
    [IO.File]::WriteAllText($agentPath, $agentBody)

    $exe = (Get-Command powershell.exe).Source
    $cmdLine = '"{0}" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{1}"' -f $exe, $agentPath
    $created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
        CommandLine      = $cmdLine
        CurrentDirectory = [IO.Path]::GetFullPath($Cwd)
    }
    if ($created.ReturnValue -ne 0 -or -not $created.ProcessId) {
        return [pscustomobject]@{ ok = $false; error = 'agent_spawn_failed' }
    }
    $procId = ConvertTo-BobRepoPairProcessId $created.ProcessId
    @{ seat = $Role; sessionId = $SessionId; at = [DateTime]::UtcNow.ToString('o'); agentPid = $procId } |
        ConvertTo-Json -Compress | Set-Content -LiteralPath $heartbeatPath -Encoding utf8
    return [pscustomobject]@{ ok = $true; pid = $procId; invokeMode = $InvokeMode }
}

function Start-BobRepoPairWorker {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][ValidateSet('dev', 'mrb')][string]$Role,
        [Parameter(Mandatory)][string]$Cwd,
        [Parameter(Mandatory)][string]$Repo,
        [Parameter(Mandatory)][string]$Title,
        [Parameter(Mandatory)][string]$SessionId,
        [Parameter(Mandatory)][string]$ShopNick,
        [Parameter(Mandatory)][string]$ShopChannel
    )

    if (Test-PromptSecrets -Prompt $Repo) {
        return [pscustomobject]@{ ok = $false; error = 'refuse'; reason = 'repo looks like secret' }
    }

    $cwdFull = [IO.Path]::GetFullPath($Cwd)
    $profileName = Get-BobRepoPairWorkerProfile -Role $Role
    $prof = Get-Profile -Name $profileName
    $fuel = Select-BobRepoPairFuel -Role $Role
    $invokeMode = Select-BobRepoPairInvokeMode -Role $Role -Fuel $fuel
    $model = Get-BobRepoPairWorkerModel -Role $Role -Fuel $fuel -InvokeMode $invokeMode
    $prompt = Build-BobRepoPairWorkerPrompt -Role $Role -Repo $Repo

    $dir = Get-WorkerDir $SessionId
    New-Item -ItemType Directory -Force -Path (Join-Path $dir 'outbox') | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $dir 'inbox') | Out-Null

    $integratedShop = $true
    $join = $null

    $argv = @()
    if ($invokeMode -eq 'grok-cli') {
        $argv = Normalize-BobRepoPairArgvList -Argv (Get-BobRepoPairArgv -Prompt $prompt -Cwd $cwdFull -SessionId $SessionId -Profile $prof -Model $model -Role $Role)
    }
    elseif ($invokeMode -eq 'cursor-cli') {
        $argv = @('cursor-agent', 'persist', '--rules', (Get-BobRepoPairRulesText -Role $Role), '--model', $model)
    }
    elseif ($invokeMode -eq 'grokbot') {
        $grokBotAgent = Get-BobRepoPairGrokBotAgent
        $argv = @('grokbot', 'agent.com', $grokBotAgent)
    }
    else {
        return [pscustomobject]@{ ok = $false; error = 'spawn_failed'; reason = 'no_invoke_mode' }
    }
    if (@($argv | Where-Object { [string]$_ -eq '-p' }).Count -gt 0) {
        return [pscustomobject]@{ ok = $false; error = 'spawn_failed'; reason = 'oneshot_argv' }
    }
    if (@($argv | Where-Object { [string]$_ -eq '--persistent' }).Count -gt 0) {
        return [pscustomobject]@{ ok = $false; error = 'spawn_failed'; reason = 'invented_persistent_flag' }
    }
    [IO.File]::WriteAllText((Join-Path $dir 'outbox\argv.txt'), (($argv | ForEach-Object { $_ }) -join "`n"))

    $agent = Start-BobRepoPairSeatAgent -Role $Role -Cwd $cwdFull -SessionId $SessionId -Prompt $prompt -InvokeMode $invokeMode -Model $model -Profile $prof -Argv $argv -ShopNick $ShopNick -ShopChannel $ShopChannel
    if (-not $agent.ok) {
        if ($join -and $join.pid) {
            try { Stop-ProcessTree -ProcessId ([int]$join.pid) } catch { }
        }
        return [pscustomobject]@{ ok = $false; error = 'spawn_failed'; reason = $agent.error }
    }
    $procId = $agent.pid

    if ($integratedShop) {
        $ircHome = Get-BobIrcHome
        if ($ircHome) { New-Item -ItemType Directory -Force -Path $ircHome | Out-Null }
        $manifestPath = Join-Path $ircHome ('shop-join-' + $SessionId + '.json')
        $deadline = [datetime]::UtcNow.AddSeconds(30)
        while ([datetime]::UtcNow -lt $deadline) {
            if (Test-Path -LiteralPath $manifestPath) { break }
            Start-Sleep -Milliseconds 400
        }
        if (-not (Test-Path -LiteralPath $manifestPath)) {
            try { Stop-ProcessTree -ProcessId ([int]$procId) } catch { }
            return [pscustomobject]@{ ok = $false; error = 'shop_join_failed'; reason = 'integrated_manifest_timeout' }
        }
        $join = [pscustomobject]@{ ok = $true; nick = $ShopNick; pid = $procId; manifest = $manifestPath; joinKind = 'irc_agent_worker' }
    }

    try { Copy-BobProjectSkills | Out-Null } catch { }
    Write-Audit -SessionId $SessionId -Cwd $cwdFull -Profile $profileName -Prompt $prompt

    $now = [DateTime]::UtcNow.ToString('o')
    $status = [pscustomobject]@{
        sessionId     = $SessionId
        kind          = 'persistent'
        state         = 'running'
        cwd           = $cwdFull
        title         = $Title
        updatedAt     = $now
        pid           = $procId
        agentPid      = $procId
        lastHeartbeat = $now
        fuel          = $fuel
        model         = $model
        role          = $Role
        shopNick      = $ShopNick
        shopChannel   = $ShopChannel
        shopJoinPid   = $(if ($join -and $join.pid) { $join.pid } else { $null })
        ircJoinManifest = $(if ($join -and $join.manifest) { $join.manifest } else { $null })
        invokeMode    = $invokeMode
        transport     = $invokeMode
    }
    Write-JsonFile (Join-Path $dir 'status.json') $status

    $overlay = Read-Overlay
    $entry = [pscustomobject]@{
        sessionId   = $SessionId
        title       = $Title
        cwd         = $cwdFull
        kind        = 'persistent'
        profile     = $profileName
        createdAt   = $now
        pid         = $procId
        shopNick    = $ShopNick
        shopChannel = $ShopChannel
        fuel        = $fuel
        model       = $model
        role        = $Role
        invokeMode  = $invokeMode
    }
    $workers = @($overlay.workers | Where-Object { $_.sessionId -ne $SessionId })
    $workers += $entry
    $overlay | Add-Member -NotePropertyName workers -NotePropertyValue $workers -Force
    Write-Overlay $overlay

    return [pscustomobject]@{
        ok          = $true
        sessionId   = $SessionId
        pid         = $procId
        processGone = $false
        kind        = 'persistent'
        fuel        = $fuel
        model       = $model
        shopNick    = $ShopNick
        argv        = $argv
        invokeMode  = $invokeMode
    }
}
