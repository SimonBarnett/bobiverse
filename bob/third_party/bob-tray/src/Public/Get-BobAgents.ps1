function Get-BobAgents {
    [CmdletBinding()]
    param()
    if (-not (Test-GrokBotAvailable)) {
        return @()
    }
    $r = Invoke-GrokBotApi -Action list -TimeoutSec 30
    if ($r.Parsed -and $r.Parsed.agents) {
        return @($r.Parsed.agents)
    }
    return @()
}
