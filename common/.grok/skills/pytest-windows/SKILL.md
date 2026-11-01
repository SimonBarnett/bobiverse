---
name: pytest-windows
description: >
  Windows pytest basetemp / tmp_path playbook for Bobiverse seats: locked
  D:\Temp\pytest-of-* WinError 5, isolated --basetemp, FR #5422 cleanup, FR #5692
  auto-redirect. Use when pytest tmp_path Access denied or sessionfinish cleanup fails.
github: https://github.com/SimonBarnett/bobiverse
---

# pytest on Windows (Bobiverse)

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap you find to the intake webhook in the
>    SAME turn. Never leave a finding unfiled, never "note it for later", never skip it because it is small.
> 2. File with the intake webhook (no secret or login needed; `POST https://irc.ntsa.uk/bob/v1/intake`; offline it is
>    queued locally and retried):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
>    (`-Kind issue|fr|skill|harvest`; always pass an explicit `-Repo owner/name`).
> 3. BEFORE finishing ANY debugging session run the harvest step:
>    `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "what broke / what fixed it" -Lesson "one learned playbook line"`
>    then `.\scripts\Invoke-BobiverseHarvest.ps1 -Flush` to resend anything that was queued while offline.
> 4. Never put a token, password, SASL/NickServ secret, key or private hostname in a filing, a skill or a log.

## Locked ``pytest-of-*`` (FR #5692)

Symptom: ``PermissionError: [WinError 5] Access is denied: 'D:\\Temp\\pytest-of-simon'`` during
``tmp_path`` / ``tmp_path_factory`` setup, or a hang on ``os.scandir`` of that tree.

Root conftest calls ``crash_report.ensure_writable_pytest_basetemp``: when the default
``%TEMP%/pytest-of-<user>`` probe fails or times out, pytest ``basetemp`` is set to
``%LOCALAPPDATA%\Temp\pytest-basetemp-<user>\pytest-<pid>``.

Manual override (any seat):

```powershell
$bt = Join-Path $env:LOCALAPPDATA "Temp\pytest-job"
New-Item -ItemType Directory -Force -Path $bt | Out-Null
python -m pytest --basetemp $bt path\to\tests -q
```

Or point TEMP away from the locked tree:

```powershell
$t = Join-Path $env:LOCALAPPDATA "Temp\pytest-temp"
New-Item -ItemType Directory -Force -Path $t | Out-Null
$env:TEMP = $t; $env:TMP = $t; $env:TMPDIR = $t
```

Do not hand-delete arbitrary ``C:\ai\*`` trees to free space (FR #2727).

## Sessionfinish cleanup (FR #5422 / #2535)

WinError 5/32/448 on ``pytest-current`` during symlink cleanup is swallowed via
``crash_report.wrap_cleanup_dead_symlinks`` so a green suite does not exit 1.

## Harvested lessons (intake)

- FR #5692: root conftest auto-sets basetemp when ``pytest-of-*`` is Access-denied or probe-hangs; prefer LOCALAPPDATA Temp over locked D:\Temp\pytest-of-<user>.
