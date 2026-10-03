<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/utf8-no-bom.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# UTF-8 without BOM (FR #347)

## Why

Windows PowerShell 5 `Set-Content` / `Out-File` / `Add-Content -Encoding UTF8` writes a **BOM**. Default `Get-Content` often reads UTF-8 as ANSI (cp1252). Round-tripping turns em-dashes into `(mojibake)` (seen on agentic_irc README / gh-Jeeves README).

## Worker rule (CAST IRON)

Read and write text as **UTF-8 with no BOM**.

In PS5:

```powershell
. .\tools\Utf8NoBom.ps1
Write-Utf8NoBomFile -Path $p -Content $s
$text = Read-Utf8NoBomFile -Path $p
Add-Utf8NoBomLine -Path $outbox -Line 'PRIVMSG #ionos :ACK ...'
```

Or:

```powershell
$utf8 = New-Object System.Text.UTF8Encoding $false
[IO.File]::WriteAllText($p, $s, $utf8)
[IO.File]::ReadAllText($p, $utf8)
```

Prefer `git` / Python for multi-file edits. Never `Get-Content | Set-Content` without explicit encodings.

## Check

```powershell
python tools/check_utf8_mojibake.py --root .
# or
python -m pytest -q tests/test_md_utf8_no_mojibake.py
powershell -NoProfile -File tests/BT0utf8-no-bom-347.ps1
```

## Adopt in other fleet repos

| Repo | Status |
|------|--------|
| `SimonBarnett/agentic_irc` | Has `tests/test_md_utf8_no_mojibake.py` (FR #227) |
| `SimonBarnett/agentic_build` | This FR (#347): `tools/check_utf8_mojibake.py` + pytest + `tools/Utf8NoBom.ps1` |
| `SimonBarnett/gh-Jeeves` | Copy the pytest or `check_utf8_mojibake.py` (related #55) |
| `SimonBarnett/AgentMonitor` | Same copy when editing markdown from PS5 seats |
