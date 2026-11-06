# FR #6109: HSwap overlay then prune files (and empty dirs) not in the pack.
# Copy-only overlays left removed kit paths such as sdk\priority-web-sdk on the target.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $PackRoot,

    [Parameter(Mandatory = $true)]
    [string] $TargetRoot
)

$ErrorActionPreference = 'Stop'
$pack = [IO.Path]::GetFullPath($PackRoot).TrimEnd('\')
$dest = [IO.Path]::GetFullPath($TargetRoot).TrimEnd('\')
if ($pack -eq $dest) {
    throw "pack and target must differ: $pack"
}
$sep = [IO.Path]::DirectorySeparatorChar
if ($pack.StartsWith($dest + $sep, [StringComparison]::OrdinalIgnoreCase) -or
    $dest.StartsWith($pack + $sep, [StringComparison]::OrdinalIgnoreCase)) {
    throw "pack and target must not nest: pack=$pack target=$dest"
}
if (-not (Test-Path -LiteralPath $pack)) {
    throw "pack missing: $pack"
}
if (-not (Test-Path -LiteralPath $dest)) {
    New-Item -ItemType Directory -Path $dest | Out-Null
}

Copy-Item -Path (Join-Path $pack '*') -Destination $dest -Recurse -Force

$wanted = @{}
Get-ChildItem -LiteralPath $pack -Recurse -File -Force | ForEach-Object {
    $rel = $_.FullName.Substring($pack.Length).TrimStart('\', '/')
    $wanted[$rel.Replace('/', '\').ToLowerInvariant()] = $true
}

Get-ChildItem -LiteralPath $dest -Recurse -File -Force | ForEach-Object {
    $rel = $_.FullName.Substring($dest.Length).TrimStart('\', '/')
    $key = $rel.Replace('/', '\').ToLowerInvariant()
    if (-not $wanted.ContainsKey($key)) {
        Remove-Item -LiteralPath $_.FullName -Force
    }
}

Get-ChildItem -LiteralPath $dest -Recurse -Directory |
    Sort-Object { $_.FullName.Length } -Descending |
    ForEach-Object {
        if (-not (Get-ChildItem -LiteralPath $_.FullName -Force | Select-Object -First 1)) {
            Remove-Item -LiteralPath $_.FullName -Force -Recurse -ErrorAction SilentlyContinue
        }
    }

Write-Output 'hswap-ok'
