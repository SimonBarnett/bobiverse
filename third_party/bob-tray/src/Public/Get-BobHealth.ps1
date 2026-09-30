function Get-BobHealth {
    [CmdletBinding()]
    param()

    $root = Initialize-BridgeRoot
    $overlay = Read-Overlay
    $exe = Get-GrokExe
    $installed = [bool]($exe -and (Test-Path $exe))
    $version = $null
    $loggedIn = $false
    if ($installed) {
        try {
            $r = Invoke-Grok -Args @('version') -WorkingDirectory $root -TimeoutSec 30
            if ($r.ExitCode -eq 0 -and $r.Stdout) {
                $version = ($r.Stdout.Trim() -split "`r?`n")[0]
                $loggedIn = $true
            }
            else {
                $r2 = Invoke-Grok -Args @('--version') -WorkingDirectory $root -TimeoutSec 30
                if ($r2.ExitCode -eq 0 -and $r2.Stdout) {
                    $version = ($r2.Stdout.Trim() -split "`r?`n")[0]
                    $loggedIn = $true
                }
            }
        }
        catch {
            $installed = $false
        }
    }

    $bot = $null
    $botOk = $false
    if (-not (Test-BobUsesFakeGrok) -and (Test-GrokBotAvailable)) {
        try {
            $hr = Invoke-GrokBotApi -Action health -TimeoutSec 30
            if ($hr.Parsed) { $bot = $hr.Parsed }
            $botOk = [bool]($bot -and $bot.ok -and $bot.signedIn)
        }
        catch { $botOk = $false }
    }

    $ok = ($installed -and $loggedIn) -or $botOk
    if ($botOk -and -not $version) {
        $version = [string]$bot.appVersion
        $loggedIn = $true
        $installed = $true
    }
    $rec = Get-BobMachineRecord
    $age = Get-BobLastSeenAgeSec -Record $rec
    $watcherUp = Test-BobWatcherUp
    $ghPosting = $null
    try { $ghPosting = Get-BobGhPostingReadiness } catch { $ghPosting = $null }
    return [pscustomobject]@{
        ok                = $ok
        grok_installed    = $installed
        logged_in         = $loggedIn
        grok_version      = $version
        worker_count      = @($overlay.workers).Count
        leader_up         = $null
        machine           = $env:COMPUTERNAME
        transport         = $(if ($botOk) { 'grokbot' } elseif ($installed) { 'cli' } else { $null })
        grokbot           = $bot
        watcher_up        = $watcherUp
        last_seen         = $(if ($rec) { [string]$rec.lastSeen } else { $null })
        last_seen_age_sec = $age
        gh_posting        = $ghPosting
    }
}
