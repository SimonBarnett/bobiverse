# jeeves.exe - chair + BobCallback one process (FR #1993)

Living architecture FR: https://github.com/SimonBarnett/bobiverse/issues/1993

`require_machine: ionos`

## Goal

Ship **ircJeeves as a frozen Windows executable** (`jeeves.exe`) that runs **chair + BobCallback in one process**, stays fully deterministic (no LLM in the service), keeps IIS to `127.0.0.1:7700` webhooks rock-solid, and can **diagnose and heal itself** with a built-in test matrix.

Operator choice (2026-10-04): **Chair + BobCallback together** (first ship).

## Why

Two processes (NSSM `ircJeeves` + scheduled `BobCallback`) share `~\.bobiverse\digest.lock` and `git-claim.lock`. Short lock waits caused `err=queue`, resync blocked, INTAKE 502, and dual-supervisor heal races (#1767 #1811 #1871 #1935).

## Process model

```text
jeeves.exe  (PyInstaller onefile; same pattern as bob-worker.exe / bob-ear.exe)
  +-- mode chair+http     DEFAULT service entry (one process)
  |     +-- IRC chair thread/loop  (irc_agent --chair)
  |     +-- HTTP :7700             (bobcallback routes in-process)
  +-- mode self-test               exit 0/1/2, JSON lines, no IRC mutate
  +-- mode heal                    deterministic repairs only (allowlist)
  +-- mode callback-only           optional debug / rollback

NSSM service ircJeeves -> jeeves.exe --chair --http 127.0.0.1:7700 --home <chair> --digest-home <bobiverse>
BobCallback scheduled task -> REMOVED (or thin watchdog calling --self-test)
BobIrcd / Ergo -> UNCHANGED
IIS ARR -> still proxies to 127.0.0.1:7700
```

### Single-process lock model (CAST IRON)

- **One writer** for `queue.json` / claim lock: in-process `threading.RLock` shared by HTTP + chair; on-disk `git-claim.lock` only for cross-process / legacy tools.
- Digest lock: chair updates and HTTP `/report` share an in-process digest mutex; break foreign locks only for other PIDs.
- Refuse second instance: bind `:7700` exclusive + named Windows mutex `Global\BobiverseJeeves-<digestHomeHash>`; second start exits **2** with JSON `{ok:false,err:"already_running"}`.

## CLI

```text
jeeves.exe --self-test [--json] [--check locks|http|queue|imports|health|offer]
jeeves.exe --heal [--dry-run] [--force-orphan-busy] [--json]
jeeves.exe --chair --http 127.0.0.1:7700 --home <chair> --digest-home <bobiverse> --nick Jeeves
jeeves.exe --http-only --bind 127.0.0.1 --port 7700 --home <digest>
```

Exit codes match `Invoke-JeevesMonitorCheck`: **0=ok, 1=finding, 2=error**.

### WP2 self-test / heal (landed)

### WP3 pack + MSI cutover (landed - FR #2301)

- `Build-Jeeves.ps1` freezes `jeeves_main.py` to `jeeves.exe` (hidden imports for chair/shop/callback/monitor).
- `Pack-BobiverseRelease` stages `jeeves\jeeves.exe` (`-SkipJeevesExe` only with `-SkipMsi`).
- `Install-Jeeves` NSSM Application = `jeeves.exe --chair --http 127.0.0.1:7700 --home <chair> --digest-home <digest>` when the exe is present; skips Python `BobCallback` task (in-proc HTTP). Legacy powershell `Start-Jeeves.ps1` remains if exe missing.

- `--self-test` default checks: `imports`, `locks`, `http` (:7700 listen), `queue`, `offer` (focus/machine empty breakdown). Add `--check health` to run `tools/monitor/health.py` as a library.
- `--heal` allowlist: break stale `git-claim.lock`, `bobreport.break_stale_digest_lock`, report HTTP/health/offer; never BobIrcd. `--force-orphan-busy` only when `accepted` is empty (still report-first; no default `clear_seat_doing`).
- Shop empty reply: `format_nothing_queued` is ALWAYS the single short line `<nick>: nothing queued` (Jeeves must hand out work, never a summary). The breakdown `format_empty_offer_detail` (`0 offerable under focus (N unaccepted, X out-of-focus, Y require_machine, self_mrb=..., ledger=..., sticky=...)`) goes to the chair log only (FR #2309). Sticky same-nick MRB offers without ACK stop refreshing `offered_ts` and clear after `OFFER_STICKY_MAX` rebroadcasts.

## Acceptance metrics

| Id | Metric | Target |
|----|--------|--------|
| E1 | Single listener | Exactly one `:7700` LISTEN while service Running |
| E2 | Intake under load | Public `POST /bob/v1/intake` -> 2xx for 30 sequential posts with chair resync running |
| E3 | No `err=queue` spam | Zero `GIT fail ... err=queue` for 1h under synthetic git ping storm |
| E4 | Self-test gate | `jeeves.exe --self-test` exit 0 on healthy box; CI runs subset offline |
| E5 | MSI cutover | Fresh install runs exe; BobCallback task absent or disabled |

## Work packages

| WP | Scope | Status |
|----|-------|--------|
| WP0 | This spec + acceptance (docs) | landed (PR #2270; append evidence on living #1993) |
| WP1 | In-process HTTP + chair entry (`jeeves_main`) + in-proc queue RLock | landed (PR #2270 foundation) |
| WP2 | Diagnostics + heal CLI + monitor scripts as libraries; empty-offer wording | landed (CLI; service-loop rebind stays in-process when exe is the service) |
| WP3 | `Build-Jeeves.ps1` + MSI/NSSM cutover | landed (FR #2301; Refs #1993) |
| WP4 | Deterministic two-worker queue storm harness + ionos cutover checklist | harness landed (FR #2302); live ionos cutover evidence 2026-10-04 in `jeeves/docs/evidence/fr1993-ionos-cutover-2026-10-04.md; exe tip redeploy 2026-10-04 evening: `jeeves/docs/evidence/fr1993-exe-redeploy-2026-10-04.md`` |

CAST IRON: living FR #1993 stays open until E1-E5 + cutover are done. Partial WP PRs use **Refs** `#1993`, never `Closes` (except dedicated child FRs like #2302 for the offline harness, which do not replace #1993).

## WP4 storm harness (FR #2302)

Any machine can run the offline harness (no `require_machine` pin on #2302):

```text
python common/scripts/jeeves_wp4_storm.py --home %TEMP%\wp4-storm --seed 1 --pings 50 --machines marchhare,flamingo --workers-per-machine 2 --out storm-summary.json
```

Acceptance the harness proves offline:

- Same seed -> same enqueue id schedule and exact done-id multiset (50/50 accounted, no duplicates/lost).
- With in-process queue RLock enabled: zero `error:queue-*` / lock-timeout under concurrent enqueue + two workers per machine claim/DONE.
- Machine-readable JSON summary (`ok`, `failures`, `event_log`, `done_ids`).

### Final ionos verification checklist (live seat; append evidence on living #1993)

1. Back up install tree, queue/digest state, NSSM parameters.
2. WP3 MSI/exe cutover: one Jeeves PID, LISTEN `127.0.0.1:7700`, intake 202, no supervised Python callback leftover.
3. Run harness against the live digest home (or mirror) with `--pings 50` and two workers per machine; then repeat after controlled Jeeves restart.
4. Confirm zero `err=queue` / lock-timeout, zero unaccounted ACK/DONE/NACK/GIVEUP rows; attach `storm-summary.json` + logs.
5. Leave Ergo / `BobIrcd` untouched. Append evidence on living #1993.

## Heal allowlist

| Check | Heal |
|-------|------|
| `:7700` LISTEN + GET report | restart HTTP thread / rebind (in-process); never BobIrcd |
| Public ARR report/intake | announce only |
| `git-claim.lock` stale/foreign | break if age>threshold and holder != self |
| Dual instance | exit / refuse second start |
| Idle seats vs offerable | **report only** (keep seats busy) |
| Seats stuck doing | report only unless `--heal --force-orphan-busy` and accepted empty |
| Empty offer / missing pull | report; in-proc resync if token present |
| Focus / stale digest / GIVEUP / stuck accepted | report only |

## Explicit non-goals

- Embedding Ergo / touching `BobIrcd`
- LLM inside the service
- Monitor `clear_seat_doing` as default heal (CAST IRON keep seats busy #1967)
- Removing IIS ARR in WP1 - WP3 (keep ARR; harden backend)

## Success definition

Operators stop babysitting supervised Python; `jeeves.exe` is the only Jeeves runtime; webhooks stay up through resync; `jeeves.exe --self-test` is the first response to any chair/webhook incident; seats stay busy unless a true orphan heal is explicitly forced.

## Evidence append — FR #2352 restart verify (2026-10-05)

See `jeeves/docs/evidence/fr2352-restart-verify-2026-10-05.md`: tip rebuild + ircJeeves-only recycle; covering merges #2342/#2348 confirmed; local intake 202; BobIrcd untouched.
