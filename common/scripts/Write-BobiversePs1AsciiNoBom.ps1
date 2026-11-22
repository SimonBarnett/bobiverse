# FR #8765: write *.ps1 as UTF-8 without BOM after ASCII sanitization.
# Replaces U+2014/U+2013/smart quotes/ellipsis/nbsp; refuses leftover non-ASCII.
# Prefer this over Set-Content -Encoding utf8 (BOM) or raw WriteAllText with em dashes.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $Path,

    [Parameter(Mandatory = $true)]
    [AllowEmptyString()]
    [string] $Value
)

$ErrorActionPreference = 'Stop'

function ConvertTo-BobiversePs1Ascii([string] $Text) {
    if ($null -eq $Text) { return '' }
    $t = $Text
    $t = $t.Replace([string][char]0x2014, '-')   # em dash
    $t = $t.Replace([string][char]0x2013, '-')   # en dash
    $t = $t.Replace([string][char]0x2018, "'")  # left single
    $t = $t.Replace([string][char]0x2019, "'")  # right single
    $t = $t.Replace([string][char]0x201C, '"')  # left double
    $t = $t.Replace([string][char]0x201D, '"')  # right double
    $t = $t.Replace([string][char]0x2026, '...') # ellipsis
    $t = $t.Replace([string][char]0x00A0, ' ')  # nbsp
    return $t
}

$cleaned = ConvertTo-BobiversePs1Ascii -Text $Value
$bad = New-Object System.Collections.Generic.List[string]
foreach ($ch in $cleaned.ToCharArray()) {
    if ([int][char]$ch -gt 127) {
        $bad.Add(('U+{0:X4}' -f [int][char]$ch)) | Out-Null
        if ($bad.Count -ge 8) { break }
    }
}
if ($bad.Count -gt 0) {
    throw ("non-ASCII remains after sanitize in {0}: {1} (prefer ASCII - / ' / `" only for *.ps1; FR #8765)" -f $Path, ($bad -join ' '))
}

$parent = Split-Path -Parent $Path
if ($parent -and -not (Test-Path -LiteralPath $parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}
$utf8 = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($Path, $cleaned, $utf8)
