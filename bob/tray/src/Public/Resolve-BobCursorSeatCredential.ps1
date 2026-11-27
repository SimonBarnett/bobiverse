function Resolve-BobCursorSeatCredential {
    <#
    FR #10001: Cursor on this seat uses this machine's login or CURSOR_API_KEY.
    The key value is never returned and never written to the pipeline.
    #>
    $local = [Environment]::GetEnvironmentVariable('CURSOR_API_KEY', 'User')
    if ([string]::IsNullOrWhiteSpace($local)) {
        $local = [Environment]::GetEnvironmentVariable('CURSOR_API_KEY', 'Process')
    }
    $hasKey = -not [string]::IsNullOrWhiteSpace($local)
    $loginDir = Join-Path $env:USERPROFILE '.cursor'
    $hasLogin = Test-Path -LiteralPath $loginDir
    $source = 'none'
    if ($hasKey) { $source = 'local-env' }
    elseif ($hasLogin) { $source = 'local-login' }
    [pscustomobject]@{
        HasLocalKey   = [bool]$hasKey
        HasLocalLogin = [bool]$hasLogin
        Source        = $source
    }
}
