# FR #4363: share-safe append to seat/ear outbox.txt under concurrent drain.
# bob-worker drain_outbox does os.replace while agents often Add-Content; WinPS
# then throws "Stream was not readable" / GetContentWriterArgumentError.
# Prefer this helper (FileShare.ReadWrite + retry) over bare Add-Content.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $Path,

    [Parameter(Mandatory = $true)]
    [string] $Line,

    [int] $Retries = 8,

    [int] $DelayMs = 50
)

$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding $false
$payload = ([string]$Line).TrimEnd("`r", "`n") + "`n"
$bytes = $utf8.GetBytes($payload)
$parent = Split-Path -Parent $Path

for ($i = 0; $i -lt $Retries; $i++) {
    try {
        if ($parent -and -not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }
        if (-not (Test-Path -LiteralPath $Path)) {
            [System.IO.File]::WriteAllText($Path, '', $utf8)
        }
        $fs = [System.IO.File]::Open(
            $Path,
            [System.IO.FileMode]::Append,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::ReadWrite
        )
        try {
            $fs.Write($bytes, 0, $bytes.Length)
            $fs.Flush()
        }
        finally {
            $fs.Dispose()
        }
        return
    }
    catch {
        if ($i -ge ($Retries - 1)) {
            throw
        }
        Start-Sleep -Milliseconds ($DelayMs * ($i + 1))
    }
}
