# FR #9044: restore tools\bob-tray.exe from bob-tray.exe.clickfix-park and keep the park.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$life = Join-Path $repo 'tray\tools\BobTrayLifecycle.ps1'
if (-not (Test-Path -LiteralPath $life)) { throw "missing $life" }
. $life
if (-not (Get-Command Restore-BobTrayExeFromClickfixPark -ErrorAction SilentlyContinue)) {
    throw 'Restore-BobTrayExeFromClickfixPark missing'
}

$root = Join-Path $PSScriptRoot '.fr9044-park'
$tools = Join-Path $root 'tools'
if (Test-Path -LiteralPath $root) { Remove-Item -LiteralPath $root -Recurse -Force }
New-Item -ItemType Directory -Force -Path $tools | Out-Null
$live = Join-Path $tools 'bob-tray.exe'
$park = Join-Path $tools 'bob-tray.exe.clickfix-park'
$bytes = [byte[]](0x4D, 0x5A, 0x90, 0x00)
[IO.File]::WriteAllBytes($park, $bytes)

$got = Restore-BobTrayExeFromClickfixPark -Root $root
if ($got -ne $live) { throw "expected live path, got $got" }
if (-not [IO.File]::Exists($live)) { throw 'live exe missing after restore' }
if (-not [IO.File]::Exists($park)) { throw 'park backup was removed' }
$liveBytes = [IO.File]::ReadAllBytes($live)
if ($liveBytes.Length -ne $bytes.Length) { throw 'live copy length mismatch' }

$again = Restore-BobTrayExeFromClickfixPark -Root $root
if ($again -ne $live) { throw 'second call should keep the live exe' }
if (-not [IO.File]::Exists($park)) { throw 'park missing after second call' }

Remove-Item -LiteralPath $root -Recurse -Force
Write-Output 'FR9044 ok'
