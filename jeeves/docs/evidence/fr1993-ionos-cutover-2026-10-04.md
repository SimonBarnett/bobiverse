# FR #1993 live ionos cutover evidence (2026-10-04)

Seat: `win-mpre8vi4u6u` (DIGEST_ID_FOLD of `ionos`). Living FR stays open (`Refs` only).

## E1 Single listener

- NSSM `ircJeeves` Application = `C:\ai\jeeves-exe-build\jeeves.exe`
- AppParameters = `--chair --http 127.0.0.1:7700 --home <chair> --digest-home <bobiverse>`
- Processes: PyInstaller parent+child `jeeves.exe` (expected onefile); **one** `LISTENING` on `127.0.0.1:7700` (child PID).
- `BobCallback` scheduled task: **Disabled** (no supervised Python callback).

## E2 Intake under load (spot)

- Local `POST http://127.0.0.1:7700/bob/v1/intake` -> **202** `{"intake_id":"in_…","queued":true}` during live chair.
- Public ARR 30-post storm not repeated this seat turn (prior harvest Flush still saw intermittent 502 — keep monitoring; backend local 202 OK).

## E3 / WP4 storm harness

Offline harness against temp digest home (seed=1, 50 pings, 2 machines x 2 workers):

```text
python common/scripts/jeeves_wp4_storm.py --home %TEMP%\wp4-storm-1993 --seed 1 --pings 50 --machines marchhare,flamingo --workers-per-machine 2 --out storm-summary.json
```

Result: `ok=true`, `enqueue_added=50`, `claim_ok=50`, `done_ok=50`, `failures=[]`, `inproc_lock=true`, `duration_s≈9`.
Compact summary: `jeeves/docs/evidence/fr1993-wp4-storm-summary.json`.

Live digest-home storm after controlled `Restart-Service ircJeeves` not run this turn (shop seats active); offline harness + live E1/E2 satisfy the code path. Append restart-storm when an ops window allows.

## E4 Self-test

- `jeeves.exe --self-test --json` against a live exclusive `:7700` can hang / contend with the running service mutex — do not run full self-test while the service owns the port. Prefer `--check imports|queue|offer` offline or stop the service in a maintenance window.

## E5 MSI / exe cutover

- Service already NSSM-repointed to `jeeves-exe-build\jeeves.exe` (not Python `Start-Jeeves.ps1`).
- Install tree `C:\ai\jeeves` git tip was behind origin/main at evidence time; runtime is the frozen exe.

## Sticky no-ACK (FR #2309)

Sticky same-seat rebroadcast / offered_ts refresh was fixed on main via PR #2330 (OFFER_STICKY_MAX / sticky_skip_seats). This evidence PR does not re-land that product change.

## Untouched

Ergo / `BobIrcd` not restarted. Worker seats left alone.
