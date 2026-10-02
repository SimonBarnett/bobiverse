function Test-SameCwd {
    param(
        [Parameter(Mandatory)][string]$Cwd,
        $Overlay
    )
    if (-not $Overlay) { $Overlay = Read-Overlay }
    $full = [IO.Path]::GetFullPath($Cwd)
    $hits = @()
    foreach ($w in @($Overlay.workers)) {
        if (-not $w.cwd) { continue }
        try {
            $other = [IO.Path]::GetFullPath($w.cwd)
        }
        catch {
            $other = [string]$w.cwd
        }
        if ([string]::Equals($other, $full, [StringComparison]::OrdinalIgnoreCase)) {
            $hits += $w
        }
    }
    return $hits
}

function Test-PromptSecrets {
    param([string]$Prompt)
    if (-not $Prompt) { return $false }
    # Only refuse assignment / env dumps — not instructional mentions.
    # Matches: password=secret, password = secret, XAI_API_KEY=..., $env:XAI_API_KEY=...
    if ($Prompt -match '(?i)(?:^|[^\w])password\s*=\s*\S') {
        return $true
    }
    if ($Prompt -match '(?i)(?:\$env:)?XAI_API_KEY\s*=\s*\S') {
        return $true
    }
    if ($Prompt -match '(?i)export\s+(?:\$env:)?XAI_API_KEY\s+\S') {
        return $true
    }
    return $false
}
