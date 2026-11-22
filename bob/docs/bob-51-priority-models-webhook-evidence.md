# BOB-51 / FR #8696 evidence: Priority launch uses models webhook row

**Issue:** https://github.com/SimonBarnett/bobiverse/issues/8696  
**Slice:** Agents > Priority: models webhook settings (Success S1)

## S1

Launch (dry-run) uses the **Priority** row from `GET /bob/v1/models` (or a fixture of that document).

## How measured

1. Fixture or live webhook JSON includes an agent row with `id`/`agent`/`name` = `priority`.
2. `Invoke-BobPriorityModelsDryRun` resolves that row and writes:

   `%LOCALAPPDATA%\Bobiverse\logs\priority-models-dry-run.log`

   (override with `BOB_PRIORITY_MODELS_DRYRUN_LOG`).

3. Log lines cite `webhook=...`, `agent=priority`, `model=...`, `source=models-webhook-priority-row`.

## Dry-run

```powershell
Import-Module <bob>/tray/src/BobBridge.psd1 -Force
$env:BOB_MODELS_WEBHOOK_FIXTURE = '<path-to-fixture.json>'
Invoke-BobPriorityModelsDryRun
Get-Content $env:LOCALAPPDATA\Bobiverse\logs\priority-models-dry-run.log
```

## Fail-when

Ignores webhook (hard-coded model with no Priority row resolution).

## Depends-on (soft for dry-run)

- BOB-01 produces live `/bob/v1/models` (fixture covers until then).
- BOB-15 / BOB-50 wire full Priority exe start; this slice only proves the Priority webhook row is selected for launch settings.