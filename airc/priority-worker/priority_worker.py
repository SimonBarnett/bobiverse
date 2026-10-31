"""Service-owned Priority Web SDK worker (FR #5283 / FR #5286).

Lives under the Airc install tree. Not a standalone PriorityClient.exe.
Invocation is only via the Airc Priority module (env AIRC_PRIORITY_OWNED=1
or --from-airc).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
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


def _prp_path(prep_dir: str, exec_id: int | str) -> Path:
    base = Path(prep_dir)
    primary = base / ("d{0}.prp".format(exec_id))
    if primary.is_file():
        return primary
    alt = base / ("d{0}.p".format(exec_id))
    return alt if alt.is_file() else primary


def _stat_mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime if path.is_file() else None
    except OSError:
        return None


def cred_present_via_fetcher(
    target: str,
    *,
    fetcher: Callable[[str], str] | None = None,
) -> bool:
    """True when CredMan has a non-empty secret for target. Never returns the secret."""
    if not (target or "").strip():
        return False
    if fetcher is None:
        return False
    try:
        secret = fetcher(target)
    except Exception:  # noqa: BLE001 - missing/empty/error => absent
        return False
    return bool(secret)


def build_default_prepare_hooks(
    *,
    cred_fetcher: Callable[[str], str] | None = None,
    lock_reader: Callable[..., dict | None] | None = None,
    sdk_exec: Callable[..., dict] | None = None,
    prp_stat: Callable[..., float | None] | None = None,
) -> dict[str, Any]:
    """Hooks for ``run_priority_prepare`` that probe CredMan / SQL / .prp / SDK.

    Callables are injectable for tests. Production console wires CredMan + sqlcmd
    + node mjs (see ``airc_console``). Never SQL-fakes UPD; never logs passwords.
    """
    state: dict[str, Any] = {}

    def cred_present(target: str) -> bool:
        return cred_present_via_fetcher(target, fetcher=cred_fetcher)

    def _read_lock(ename: str, instance: dict) -> dict | None:
        if lock_reader is None:
            return None
        return lock_reader(ename=ename, instance=instance, exec_type="P")

    def read_upd(*, ename: str, instance: dict, **_k: Any) -> str:
        lock = _read_lock(ename, instance)
        if not lock:
            state["lock_missing"] = True
            return ""
        state["exec_id"] = lock.get("exec_id")
        state["upd"] = str(lock.get("upd") or "").strip().upper()
        return state["upd"]

    def _mtime_for(ename: str, instance: dict) -> float:
        exec_id = state.get("exec_id")
        prep = str(instance.get("prepDir") or instance.get("prep_dir") or "").strip()
        if exec_id is None or not prep:
            lock = _read_lock(ename, instance)
            if lock:
                state["exec_id"] = lock.get("exec_id")
                exec_id = state["exec_id"]
                if "upd" not in state:
                    state["upd"] = str(lock.get("upd") or "").strip().upper()
            prep = str(instance.get("prepDir") or instance.get("prep_dir") or "").strip()
        if exec_id is None or not prep:
            return 0.0
        if prp_stat is not None:
            mt = prp_stat(ename=ename, instance=instance, exec_id=exec_id, prep_dir=prep)
            return float(mt or 0.0)
        mt = _stat_mtime(_prp_path(prep, exec_id))
        return float(mt or 0.0)

    def prp_before(**kw: Any) -> float:
        v = _mtime_for(kw.get("ename") or "", kw.get("instance") or {})
        state["prp_before"] = v
        return v

    def prp_after(**kw: Any) -> float:
        ename = kw.get("ename") or ""
        instance = kw.get("instance") or {}
        lock = _read_lock(ename, instance)
        if lock:
            state["exec_id"] = lock.get("exec_id")
            state["upd_after"] = str(lock.get("upd") or "").strip().upper()
        return _mtime_for(ename, instance)

    def sdk(**kw: Any) -> dict:
        if sdk_exec is None:
            return {"ok": False, "path": "REPPREPDIRECT2", "reason": "sdk_hooks_missing"}
        return sdk_exec(**kw)

    return {
        "cred_present": cred_present,
        "sdk_exec": sdk,
        "read_upd": read_upd,
        "prp_mtime_before": prp_before,
        "prp_mtime_after": prp_after,
    }


def run_priority_prepare(
    ename: str,
    *,
    instance_id: str = "",
    instances: list[dict] | None = None,
    cred_present: Callable[[str], bool] | None = None,
    sdk_exec: Callable[..., dict] | None = None,
    read_upd: Callable[..., str] | None = None,
    prp_mtime_before: float | Callable[..., float] | None = None,
    prp_mtime_after: Callable[..., float] | None = None,
    proc_type: str = "P",
) -> dict[str, Any]:
    """TYPE=P named prep: EXEC REPPREPDIRECT2; success only if ok + UPD=N + .prp advanced.

    Never SQL-fakes UPD. Never uses the form-prep path for TYPE=P.
    ``prp_mtime_before`` may be a float or a callable (live walk).
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
    target = str(inst.get("credentialTarget") or inst.get("credential_target") or "").strip()
    has_cred = cred_present if cred_present is not None else (lambda _t: False)
    if not target or not has_cred(target):
        base["reason"] = "no_cred"
        return base
    # CAST IRON: TYPE=P is EXEC REPPREPDIRECT2 only (never formStart / form-prep).
    path = "REPPREPDIRECT2"
    # Capture .prp mtime BEFORE SDK so advance is meaningful.
    if callable(prp_mtime_before):
        before = float(prp_mtime_before(ename=name, instance=inst))
    elif prp_mtime_before is None:
        before = 0.0
    else:
        before = float(prp_mtime_before)
    sdk_fn = sdk_exec or (lambda **_k: {"ok": False, "path": path})
    sdk = sdk_fn(path=path, ename=name, form_prep=False, instance=inst, proc_type=proc_type)
    if not isinstance(sdk, dict) or not sdk.get("ok"):
        base["reason"] = "sdk_not_ok"
        if isinstance(sdk, dict) and sdk.get("reason"):
            base["sdk_reason"] = sdk.get("reason")
        return base
    upd_fn = read_upd or (lambda **_k: "")
    upd = str(upd_fn(ename=name, instance=inst) or "").strip().upper()
    base["upd"] = upd
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
