# jeeves.exe — chair + BobCallback one process (FR #1993)

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

## CLI (draft)

```text
jeeves.exe --self-test [--json] [--check locks|http|queue|...]
jeeves.exe --heal [--dry-run] [--force-orphan-busy]
jeeves.exe --chair --http 127.0.0.1:7700 --home <chair> --digest-home <bobiverse> --nick Jeeves
jeeves.exe --http-only --bind 127.0.0.1 --port 7700 --home <digest>
```

Exit codes match `Invoke-JeevesMonitorCheck`: **0=ok, 1=finding, 2=error**.

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
| WP0 | This spec + acceptance (docs) | this PR (append evidence on living #1993) |
| WP1 | In-process HTTP + chair entry (`jeeves_main`) + in-proc queue RLock | this PR (foundation) |
| WP2 | Diagnostics + heal CLI + service loop (monitor scripts as libraries) | next — append on #1993 (do not twin FR) |
| WP3 | `Build-Jeeves.ps1` + MSI/NSSM cutover | next — append on #1993 (do not twin FR) |
| WP4 | Ionos cutover + storm test | next — append on #1993 (`require_machine: ionos`) |

CAST IRON: living FR #1993 stays open until E1–E5 + cutover are done. Partial WP PRs use **Refs** `#1993`, never `Closes`.

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
- Removing IIS ARR in WP1–WP3 (keep ARR; harden backend)

## Success definition

Operators stop babysitting supervised Python; `jeeves.exe` is the only Jeeves runtime; webhooks stay up through resync; `jeeves.exe --self-test` is the first response to any chair/webhook incident; seats stay busy unless a true orphan heal is explicitly forced.
