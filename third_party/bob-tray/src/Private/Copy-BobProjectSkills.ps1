function Get-BobProjectSkillsRoot {
    Join-Path (Get-ModuleRoot) '.grok\skills'
}

function Copy-BobProjectSkills {
    # Put github.com/SimonBarnett/agentic_build .grok/skills into ~/.grok/skills
    # so grok.exe discovers them even when --cwd is another repo.
    if (Test-BobUsesFakeGrok) { return @() }
    $skillRoot = Get-BobProjectSkillsRoot
    if (-not (Test-Path $skillRoot)) { return @() }
    $skillDstRoot = Join-Path $env:USERPROFILE '.grok\skills'
    $copied = @()
    foreach ($dir in @(Get-ChildItem $skillRoot -Directory -ErrorAction SilentlyContinue)) {
        $src = Join-Path $dir.FullName 'SKILL.md'
        if (-not (Test-Path $src)) { continue }
        $dstDir = Join-Path $skillDstRoot $dir.Name
        New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
        Copy-Item $src (Join-Path $dstDir 'SKILL.md') -Force
        $copied += $dir.Name
    }
    return $copied
}

function Get-BobProjectSkillsHint {
    $root = Get-BobProjectSkillsRoot
    return "Skills from https://github.com/SimonBarnett/agentic_build live at $root (copied to ~/.grok/skills). Follow those SKILL.md files."
}
