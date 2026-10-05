# FR #2352 — ircJeeves tip redeploy + restart verify (2026-10-05)

Seat: `win-mpre8vi4u6u-14452` (DIGEST_ID_FOLD of ionos).

## Context

FR #2347 left restart + live confirm of stranded-pinned-MRB / CLOSED-FR skip incomplete. Assigned MRB tip #2344 was later **FAIL-superseded**; covering merges on main:

- **#2342** — sibling block ignores `require_machine`-pinned-out seats (Fixes #2339)
- **#2348** — purge CLOSED-issue FR rows before offer (Closes #2340)

## Steps

1. Confirmed tip `origin/main` @ `73a7f1d047eb2e8cadfd8131e0b57371727d9d3c` contains `_purge_closed_fr_unaccepted` + FR #2339 sibling pin skip.
2. `Build-Jeeves.ps1` → smoke `--self-test` exit 0 → `jeeves.exe` 12.1 MB.
3. Backed up live `C:\ai\jeeves-exe-build\jeeves.exe` to `jeeves.exe.bak-2352-*`.
4. **Stop-Service ircJeeves** → copy tip exe → **Start-Service ircJeeves**. Did **not** touch BobIrcd / Ergo / ircBob / worker seats.
5. Post-checks within ~1s: ircJeeves Running; one `127.0.0.1:7700` LISTEN; report HTTP 200; local POST `/bob/v1/intake` → **202**.
6. Chair log: `jeeves http listen 127.0.0.1:7700 inproc=1`; OPER OK; joined shops; webhook-health local+public up; `err=queue` count in last ~2k lines = **0**.
7. Offline gates (tip tree): `pytest test_fr2340_purge_closed_fr.py test_mrb2342_hostile_sibling_pin.py` → **10 passed**. Scratch `offer_focus_top` with `issue_open` skips closed `#2218` and offers `#2352`; sibling pin: ionos-pinned MRB not blocked for sibling ionos seat when marchhare is live.

## Results

| Check | Result |
|-------|--------|
| ircJeeves restart | PASS |
| BobIrcd / ircBob undisturbed | PASS (both Running) |
| Single :7700 LISTEN | PASS |
| Local intake 202 | PASS |
| Covering unit tests | PASS (10) |
| Closed FR skip (offline offer) | PASS |
| Sibling pin not stranded (offline) | PASS |
| Live sticky re-offer of merged #2319 | N/A — #2319 MERGED, not in queue |

## Side findings (filed)

- Accidental intake probe during verify closed as not planned: **#2360**.
- Live `queue.accepted` still held **CLOSED** FR **#2340** for marchhare after issue close — filed **#2361** (accepted-row purge gap; unaccepted purge already #2348).

## Live exe

- Path: `C:\ai\jeeves-exe-build\jeeves.exe`
- Built from tip `73a7f1d047eb2e8cadfd8131e0b57371727d9d3c`
- Size/mtime: 12719490 bytes @ 2026-10-05T00:45:03.3119269+01:00

## Could not / did not

- Full in-service `jeeves.exe --self-test` while service owns :7700 (mutex/port contend).
- Public ARR 30-post storm (deferred on living #1993).
- Did not clear orphan ACC #2340 in this PR (keep seats busy; filed #2361).