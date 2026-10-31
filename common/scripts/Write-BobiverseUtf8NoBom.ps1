# FR #5502: write UTF-8 without BOM for gh --body-file / --comment files.
# WinPS 5.1 Set-Content -Encoding utf8 prefixes EF BB BF; gh pr create then
# stores U+FEFF as the first character of the PR body (bobiverse#5501).
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $Path,

    [Parameter(Mandatory = $true)]
    [string] $Value
)

$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding $false
$parent = Split-Path -Parent $Path
if ($parent -and -not (Test-Path -LiteralPath $parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}
[System.IO.File]::WriteAllText($Path, [string]$Value, $utf8)
