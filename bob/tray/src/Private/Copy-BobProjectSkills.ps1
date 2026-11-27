function Get-BobProjectSkillsRoot {
    Join-Path (Get-ModuleRoot) '.grok\skills'
}

function Invoke-BobDagMcp {
    param([Parameter(Mandatory)]$Payload, [string]$Url = '')
    if (-not $Url) {
        if ($env:BOB_SKILL_MCP_URL) { $Url = $env:BOB_SKILL_MCP_URL }
        else { $Url = 'https://bob.ntsa.uk/mcp' }
    }
    $json = $Payload | ConvertTo-Json -Depth 8 -Compress
    return Invoke-RestMethod -Method POST -Uri $Url -ContentType 'application/json; charset=utf-8' -Body $json
}

function Copy-BobProjectSkills {
    # FR #10081: worker agents load the Bob book from the DAG MCP.
    # Do not copy SKILL.md out of the git checkout.
    if (Test-BobUsesFakeGrok) { return @() }
    $list = Invoke-BobDagMcp -Payload @{
        jsonrpc = '2.0'
        id       = 1
        method   = 'tools/call'
        params   = @{ name = 'list_catalog'; arguments = @{} }
    }
    $catalog = [string]$list.result.content[0].text | ConvertFrom-Json
    $skillDstRoot = Join-Path $env:USERPROFILE '.grok\skills'
    $copied = @()
    foreach ($row in @($catalog.skills)) {
        $name = [string]$row.name
        if (-not $name -or $name.IndexOfAny([char[]]@('\', '/', '.')) -ge 0) { continue }
        $one = Invoke-BobDagMcp -Payload @{
            jsonrpc = '2.0'
            id       = 2
            method   = 'tools/call'
            params   = @{ name = 'get_skill'; arguments = @{ name = $name } }
        }
        $md = [string](([string]$one.result.content[0].text | ConvertFrom-Json).skillMd)
        if (-not $md) { continue }
        $dstDir = Join-Path $skillDstRoot $name
        New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
        [IO.File]::WriteAllText((Join-Path $dstDir 'SKILL.md'), $md)
        $copied += $name
    }
    return $copied
}

function Get-BobProjectSkillsHint {
    return 'Worker skills load from https://bob.ntsa.uk/mcp (list_catalog, get_skill) into ~/.grok/skills. Do not clone the skill book from git.'
}
