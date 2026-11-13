# FR #7149 --- redqueen live recycleseat blocked by list-shaped digest workers

Date: 2026-11-13 (UTC). Machine: redqueen. Seat: redqueen-9160.

## What we ran

1. Confirmed post-#7126 recycle scripts on install (`67f488fc` ancestor of HEAD; `recycleseat.py` / `BobTrayRecycleSeat.ps1` tip markers present).
2. Idle sibling `redqueen-6240` (pid 6240) available; verifier `redqueen-9160` doing this FR.
3. Shop `!recycleseat redqueen-6240` from the worker nick: ear `ok=False reason=unverified` (expected; FR #5059).
4. Concurrent Jeeves chair attempts: `ok=False reason=state_unavailable` for the same seat (repeated in `C:\ai\bob\logs\stdout.log`).

## Root cause

Live `C:\ai\bob\home\digest.json` has `machines.redqueen.workers` as a **list** of `{nick,state,work}` rows (no `worker_list`).

`recycleseat._work_from_doc` assumed `workers` was a pid-keyed **dict** and called `.get` on the list:

`AttributeError: 'list' object has no attribute 'get'`

`inspect_seat_work` then returned `known=False`, so `decide` NACKed `state_unavailable` and never queued a tray request.

## Fix

Handle list-shaped `workers` (and keep the pid-map + `worker_list` paths). Tests in `common/tests/test_fr7149_recycleseat_list_workers.py`.

Against the live digest with the patched module: `redqueen-6240 known=True working=False`; `redqueen-9160 known=True working=True`.

## Residual for (e)

Frozen `bob-ear.exe` embeds `recycleseat`. After this tip is on main and the ear is redeployed (or Start-Bob selects python with the tip script), re-run authorised `!recycleseat` on an idle sibling and confirm replacement takes a normal job to DONE. Worker seats remain unverified for the command (chair/op/owner/ear only).

## Hashes (before)

- install HEAD (pre-ff): `23b74f88` (behind main; #7126 ancestor yes)
- worker `--version`: `6a68102b9dd26eb069b1236582ea5c91a81ef199`
- worker exe SHA256: `D6319C0DC6E16BAB2CF5E5F8FACCA97AE121AE784440BB4894F30863011BB282`