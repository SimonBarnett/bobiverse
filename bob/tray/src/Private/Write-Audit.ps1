function Write-Audit {
    param(
        [string]$SessionId,
        [string]$Cwd,
        [string]$Profile,
        [string]$Prompt
    )
    $root = Initialize-BridgeRoot
    $path = Join-Path $root 'audit.jsonl'
    $sha = ''
    if ($null -ne $Prompt) {
        $bytes = [Text.Encoding]::UTF8.GetBytes($Prompt)
        $hash = [Security.Cryptography.SHA256]::Create().ComputeHash($bytes)
        $sha = ([BitConverter]::ToString($hash) -replace '-', '').ToLowerInvariant()
    }
    $row = [ordered]@{
        id      = [guid]::NewGuid().ToString()
        time    = [DateTime]::UtcNow.ToString('o')
        session = $SessionId
        cwd     = $Cwd
        profile = $Profile
        sha256  = $sha
    }
    $line = ($row | ConvertTo-Json -Compress)
    if ($line -match 'XAI_API_KEY') {
        throw "Refusing to write audit line that contains XAI_API_KEY"
    }
    # FR #347: UTF-8 without BOM (PS5 Set-Content -Encoding utf8 would BOM)
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [IO.File]::AppendAllText($path, $line + [Environment]::NewLine, $utf8)
}
