function Get-BobProductRepo {
    if ($env:BOB_PRODUCT_REPO) { return [string]$env:BOB_PRODUCT_REPO.Trim() }
    return 'SimonBarnett/agentic_build'
}

function Get-BobGhExe {
    if ($env:BOB_GH_EXE) {
        if (Test-Path -LiteralPath $env:BOB_GH_EXE) { return $env:BOB_GH_EXE }
        return $null
    }
    foreach ($c in @(
            (Join-Path ${env:ProgramFiles} 'GitHub CLI\gh.exe'),
            (Join-Path ${env:ProgramFiles(x86)} 'GitHub CLI\gh.exe'),
            (Join-Path $env:LOCALAPPDATA 'GitHubCLI\gh.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\GitHub CLI\gh.exe')
        )) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }
    $cmd = Get-Command gh.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Get-BobGhPostingReadiness {
    [CmdletBinding()]
    param(
        [string]$Repo
    )
    if (-not $Repo) { $Repo = Get-BobProductRepo }
    $gh = Get-BobGhExe
    if (-not $gh) {
        return [pscustomobject]@{
            present               = $false
            authenticated         = $false
            issue_posting_ready   = $false
            gh_exe                = $null
            repo                  = $Repo
            reason                = 'gh.exe not found (winget install GitHub.cli)'
        }
    }
    & $gh auth status 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        return [pscustomobject]@{
            present               = $true
            authenticated         = $false
            issue_posting_ready   = $false
            gh_exe                = $gh
            repo                  = $Repo
            reason                = 'gh auth login required (or set GH_TOKEN / GITHUB_TOKEN with issues:write and pull_requests:write)'
        }
    }
    $null = & $gh repo view $Repo --json name -q .name 2>&1
    if ($LASTEXITCODE -ne 0) {
        return [pscustomobject]@{
            present               = $true
            authenticated         = $true
            issue_posting_ready   = $false
            gh_exe                = $gh
            repo                  = $Repo
            reason                = "cannot read repo $Repo with current gh auth (need issues:write and pull_requests:write on the product repo)"
        }
    }
    return [pscustomobject]@{
        present               = $true
        authenticated         = $true
        issue_posting_ready   = $true
        gh_exe                = $gh
        repo                  = $Repo
        reason                = $null
    }
}

function Test-BobMachineGhIssuePostingReady {
    param($Machine)
    if ($null -eq $Machine) { return $false }
    $g = $Machine.gh_posting
    if ($null -eq $g) { return $false }
    try { return [bool]$g.issue_posting_ready } catch { return $false }
}

function Test-BobGhIssuePosting {
    param(
        [Parameter(Mandatory)][string]$Repo
    )
    $r = Get-BobGhPostingReadiness -Repo $Repo
    if (-not $r.issue_posting_ready) {
        $msg = [string]$r.reason
        if ($msg -match 'gh\.exe not found') {
            throw 'MRB handoff preflight: gh.exe not found (winget install GitHub.cli). Fix GitHub CLI before spending Cursor/Grok on the review.'
        }
        if ($msg -match 'gh auth login') {
            throw 'MRB handoff preflight: gh auth login required on this worker (or set GH_TOKEN / GITHUB_TOKEN with issues:write and pull_requests:write). Fail here before starting the MRB agent.'
        }
        throw "MRB handoff preflight: $msg Fail here before starting the MRB agent."
    }
    return $r.gh_exe
}

function Set-BobGhLabelReady {
    param(
        [Parameter(Mandatory)][string]$Gh,
        [Parameter(Mandatory)][string]$Repo,
        [Parameter(Mandatory)][string]$Name,
        [string]$Color = 'ededed'
    )
    $out = & $Gh label create $Name --repo $Repo --color $Color --force 2>&1 | Out-String
    $createExit = $LASTEXITCODE
    if ($createExit -eq 0) { return $true }
    if ($out -match '(?i)already exists|name already exists') { return $true }
    $json = & $Gh label list --repo $Repo --limit 500 --json name 2>&1 | Out-String
    if ($LASTEXITCODE -eq 0 -and $json) {
        $names = @($json | ConvertFrom-Json | ForEach-Object { [string]$_.name })
        if ($names -contains $Name) { return $true }
    }
    if ($out.Trim()) {
        Write-Warning "Set-BobGhLabelReady $Name on $Repo : $out"
    }
    else {
        Write-Warning "Set-BobGhLabelReady $Name on $Repo : label create failed (exit $createExit)"
    }
    return $false
}

function Update-BobMachineGhPostingSnapshot {
    param($Record)
    if (-not $Record) { return $Record }
    try {
        $r = Get-BobGhPostingReadiness
        $snap = [pscustomobject]@{
            present               = [bool]$r.present
            authenticated         = [bool]$r.authenticated
            issue_posting_ready   = [bool]$r.issue_posting_ready
            probed_at             = [DateTime]::UtcNow.ToString('o')
        }
        $Record | Add-Member -NotePropertyName gh_posting -NotePropertyValue $snap -Force
    }
    catch { }
    return $Record
}

function Install-BobGitHubCliIfMissing {
    [CmdletBinding()]
    param()
    $before = Get-BobGhExe
    $action = 'present'
    if (-not $before) {
        $action = 'absent'
        $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
        if ($winget) {
            try {
                & winget install --id GitHub.cli -e --accept-source-agreements --accept-package-agreements --disable-interactivity 2>&1 | Out-Null
                $action = 'winget-install'
            }
            catch {
                $action = 'winget-failed'
            }
        }
        else {
            $action = 'manual-required'
        }
    }
    $readiness = Get-BobGhPostingReadiness
    return [pscustomobject]@{
        install_action        = $action
        readiness             = $readiness
    }
}
