"""Service-owned Priority Web SDK worker (FR #5283 / FR #5286).

Lives under the Airc install tree. Not a standalone PriorityClient.exe.
Invocation is only via the Airc Priority module (env AIRC_PRIORITY_OWNED=1
or --from-airc).
"""
from __future__ import annotations

import os
import sys
from typing import Any, Callable


def owned_by_airc(argv: list[str] | None = None) -> bool:
    args = list(sys.argv[1:] if argv is None else argv)
    if os.environ.get("AIRC_PRIORITY_OWNED", "").strip() == "1":
        return True
    return "--from-airc" in args


def main(argv: list[str] | None = None) -> int:
    if not owned_by_airc(argv):
        sys.stderr.write("refuse: invoke only via Airc Priority module (FR #5283)\n")
        return 2
    sys.stdout.write("ok owned=airc worker=priority-web-sdk\n")
    return 0


def _instance(instances: list[dict] | None, instance_id: str) -> dict | None:
    rows = list(instances or [])
    if not rows:
        return None
    want = (instance_id or "").strip()
    if want:
        for row in rows:
            if str(row.get("id") or "") == want:
                return row
        return None
    return rows[0]


def run_priority_prepare(
    ename: str,
    *,
    instance_id: str = "",
    instances: list[dict] | None = None,
    cred_present: Callable[[str], bool] | None = None,
    sdk_exec: Callable[..., dict] | None = None,
    read_upd: Callable[..., str] | None = None,
    prp_mtime_before: float | None = None,
    prp_mtime_after: Callable[..., float] | None = None,
    proc_type: str = "P",
) -> dict[str, Any]:
    """TYPE=P named prep: EXEC REPPREPDIRECT2; success only if ok + UPD=N + .prp advanced.

    Never SQL-fakes UPD. Never uses the form-prep path for TYPE=P.
    """
    name = (ename or "").strip()
    base: dict[str, Any] = {
        "ok": False,
        "ename": name,
        "exec": "REPPREPDIRECT2",
        "sql_faked": False,
        "prp_advanced": False,
    }
    if not name:
        base["reason"] = "name_missing"
        return base
    inst = _instance(instances, instance_id)
    if inst is None:
        base["reason"] = "instance_unknown"
        return base
    target = str(inst.get("credentialTarget") or "").strip()
    has_cred = cred_present if cred_present is not None else (lambda _t: False)
    if not target or not has_cred(target):
        base["reason"] = "no_cred"
        return base
    # CAST IRON: TYPE=P is EXEC REPPREPDIRECT2 only (never formStart / form-prep).
    path = "REPPREPDIRECT2"
    sdk_fn = sdk_exec or (lambda **_k: {"ok": False, "path": path})
    sdk = sdk_fn(path=path, ename=name, form_prep=False, instance=inst, proc_type=proc_type)
    if not isinstance(sdk, dict) or not sdk.get("ok"):
        base["reason"] = "sdk_not_ok"
        return base
    upd_fn = read_upd or (lambda **_k: "")
    upd = str(upd_fn(ename=name, instance=inst) or "").strip().upper()
    base["upd"] = upd
    before = 0.0 if prp_mtime_before is None else float(prp_mtime_before)
    after_fn = prp_mtime_after or (lambda **_k: before)
    after = float(after_fn(ename=name, instance=inst))
    base["prp_mtime_before"] = before
    base["prp_mtime_after"] = after
    advanced = after > before
    base["prp_advanced"] = advanced
    if upd != "N":
        base["reason"] = "still_unprepared"
        return base
    if not advanced:
        base["reason"] = "prp_unchanged"
        return base
    base["ok"] = True
    base["reason"] = "prepared"
    return base


if __name__ == "__main__":
    raise SystemExit(main())
