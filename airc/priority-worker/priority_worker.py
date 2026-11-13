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


def _stat_mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime if path.is_file() else None
    except OSError:
        return None


def _prep_artifact_candidates(prep_dir: str, exec_id: int | str) -> list[Path]:
    base = Path(prep_dir)
    eid = str(exec_id)
    return [base / ("d{0}.prp".format(eid)), base / ("d{0}.p".format(eid))]


def _prep_artifact_info(prep_dir: str, exec_id: int | str) -> tuple[Path, float | None]:
    """Newest existing prep artifact (``.prp`` or ``.p``) and its mtime.

    FR #6008: TYPE=R ``REPPREPDIRECT2`` rewrites ``d{id}.p`` while a stale
    ``d{id}.prp`` may still exist. Prefer the newest of the two so a real
    rewrite counts as advanced; ``prep_file`` names that artifact.
    """
    default = Path(prep_dir) / ("d{0}.prp".format(exec_id))
    best_path = default
    best_mtime: float | None = None
    for path in _prep_artifact_candidates(prep_dir, exec_id):
        mt = _stat_mtime(path)
        if mt is None:
            continue
        if best_mtime is None or mt > best_mtime:
            best_mtime = mt
            best_path = path
    return best_path, best_mtime


def _prp_path(prep_dir: str, exec_id: int | str) -> Path:
    """Path used for the prep-artifact mtime gate (newest of ``.prp`` / ``.p``)."""
    path, _mt = _prep_artifact_info(prep_dir, exec_id)
    return path


def _path_is_dir(path: str | Path) -> bool:
    try:
        return Path(path).is_dir()
    except OSError:
        return False


def _prep_under_root(root: str | Path) -> Path:
    return Path(root) / "system" / "prep"


def _read_tabula_ini_prep_dir(
    *,
    windir: str | Path | None = None,
    read_text: Callable[[Path], str] | None = None,
) -> str | None:
    """FR #5943: ``Priority Directory`` in tabula.ini is the prep folder itself."""
    import re

    bases: list[Path] = []
    if windir is not None:
        bases.append(Path(windir))
    for key in ("WINDIR", "SystemRoot"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            bases.append(Path(raw))
    bases.append(Path(r"C:\Windows"))
    seen: set[str] = set()
    reader = read_text or (lambda p: p.read_text(encoding="utf-8", errors="replace"))
    pat = re.compile(r"(?im)^\s*Priority\s+Directory\s*=\s*(.+?)\s*$")
    for base in bases:
        key = str(base).lower()
        if key in seen:
            continue
        seen.add(key)
        ini = base / "tabula.ini"
        try:
            if not ini.is_file():
                continue
            text = reader(ini)
        except OSError:
            continue
        m = pat.search(text or "")
        if not m:
            continue
        cand = m.group(1).strip().strip('"').strip("'")
        if cand:
            return cand
    return None


def resolve_prep_dir(
    instance: dict,
    *,
    path_is_dir: Callable[[str | Path], bool] | None = None,
    tabula_reader: Callable[..., str | None] | None = None,
) -> dict[str, Any]:
    """FR #5943: resolve Priority ``system\\prep`` per instance.

    ``prepDir`` / ``prep_dir`` is an optional override. When unset, derive from
    ``priorityRoot`` / install fields, ``tabula.ini`` Priority Directory, or
    ``PRIORITY_PREP_DIR`` / ``PRIORITY_ROOT`` env.

    Returns ``{path, source, tried, derived_from}`` where ``source`` is
    ``override`` | ``derived`` | ``""`` and ``tried`` lists probe names.
    """
    is_dir = path_is_dir or _path_is_dir
    tried: list[str] = []
    inst = instance if isinstance(instance, dict) else {}

    override = str(inst.get("prepDir") or inst.get("prep_dir") or "").strip()
    tried.append("override")
    if override:
        if is_dir(override):
            return {
                "path": str(Path(override)),
                "source": "override",
                "tried": tried,
                "derived_from": "",
            }
        # Explicit bad override: do not fall through to derivation (misconfig).
        return {
            "path": "",
            "source": "",
            "tried": tried,
            "derived_from": "",
            "override_invalid": True,
        }

    for key in (
        "priorityRoot",
        "priority_root",
        "installRoot",
        "install_dir",
        "installDir",
    ):
        root = str(inst.get(key) or "").strip()
        if not root:
            continue
        tried.append("priority_root")
        cand = _prep_under_root(root)
        if is_dir(cand):
            return {
                "path": str(cand),
                "source": "derived",
                "tried": tried,
                "derived_from": "priority_root",
            }
        break
    else:
        tried.append("priority_root")

    tried.append("tabula_ini")
    reader = tabula_reader or _read_tabula_ini_prep_dir
    try:
        tabula_prep = reader()
    except TypeError:
        tabula_prep = reader(windir=os.environ.get("WINDIR"))
    except Exception:  # noqa: BLE001
        tabula_prep = None
    if tabula_prep and is_dir(tabula_prep):
        return {
            "path": str(Path(tabula_prep)),
            "source": "derived",
            "tried": tried,
            "derived_from": "tabula_ini",
        }

    tried.append("env_priority_prep")
    env_prep = (os.environ.get("PRIORITY_PREP_DIR") or "").strip()
    if env_prep and is_dir(env_prep):
        return {
            "path": str(Path(env_prep)),
            "source": "derived",
            "tried": tried,
            "derived_from": "env_priority_prep",
        }

    tried.append("env_priority_root")
    for env_key in ("PRIORITY_ROOT", "PRIORITY_HOME"):
        root = (os.environ.get(env_key) or "").strip()
        if not root:
            continue
        cand = _prep_under_root(root)
        if is_dir(cand):
            return {
                "path": str(cand),
                "source": "derived",
                "tried": tried,
                "derived_from": "env_priority_root",
            }

    return {
        "path": "",
        "source": "",
        "tried": tried,
        "derived_from": "",
    }


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
    types_reader: Callable[..., list[dict]] | None = None,
    sdk_exec: Callable[..., dict] | None = None,
    prp_stat: Callable[..., float | None] | None = None,
) -> dict[str, Any]:
    """Hooks for ``run_priority_prepare`` that probe CredMan / SQL / .prp / SDK.

    Callables are injectable for tests. Production console wires CredMan + sqlcmd
    + node mjs (see ``airc_console``). Never SQL-fakes UPD; never logs passwords.

    FR #5933: ``types_reader`` lists every T$EXEC row for ENAME (all TYPEs) so
    prepare can refuse non-procedure / ambiguous names before REPPREPDIRECT2.
    """
    state: dict[str, Any] = {}

    def cred_present(target: str) -> bool:
        return cred_present_via_fetcher(target, fetcher=cred_fetcher)

    def _read_lock(
        ename: str,
        instance: dict,
        *,
        exec_type: str = "P",
        exec_id: Any = None,
    ) -> dict | None:
        if lock_reader is None:
            return None
        # FR #5946: pass exec_id when the reader accepts it; older injectables
        # (ename/instance/exec_type only) stay compatible.
        try:
            return lock_reader(
                ename=ename,
                instance=instance,
                exec_type=exec_type or "P",
                exec_id=exec_id,
            )
        except TypeError:
            return lock_reader(
                ename=ename,
                instance=instance,
                exec_type=exec_type or "P",
            )

    def read_upd(*, ename: str, instance: dict, **kw: Any) -> str:
        et = str(kw.get("exec_type") or state.get("exec_type") or "P").strip().upper() or "P"
        eid = kw.get("exec_id") if kw.get("exec_id") is not None else state.get("exec_id")
        lock = _read_lock(ename, instance, exec_type=et, exec_id=eid)
        if not lock:
            state["lock_missing"] = True
            return ""
        state["exec_id"] = lock.get("exec_id")
        state["exec_type"] = str(lock.get("exec_type") or et).strip().upper()
        state["upd"] = str(lock.get("upd") or "").strip().upper()
        return state["upd"]

    def _mtime_for(
        ename: str,
        instance: dict,
        *,
        exec_type: str = "P",
        exec_id: Any = None,
    ) -> float:
        if exec_id is not None:
            state["exec_id"] = exec_id
        if exec_type:
            state["exec_type"] = exec_type
        eid = state.get("exec_id")
        prep = str(instance.get("prepDir") or instance.get("prep_dir") or "").strip()
        if eid is None or not prep:
            lock = _read_lock(
                ename,
                instance,
                exec_type=str(state.get("exec_type") or exec_type or "P"),
                exec_id=eid,
            )
            if lock:
                state["exec_id"] = lock.get("exec_id")
                eid = state["exec_id"]
                if "upd" not in state:
                    state["upd"] = str(lock.get("upd") or "").strip().upper()
            prep = str(instance.get("prepDir") or instance.get("prep_dir") or "").strip()
        if eid is None or not prep:
            return 0.0
        if prp_stat is not None:
            mt = prp_stat(ename=ename, instance=instance, exec_id=eid, prep_dir=prep)
            return float(mt or 0.0)
        art, mt = _prep_artifact_info(prep, eid)
        state["prep_file"] = art.name
        return float(mt or 0.0)

    def prp_before(**kw: Any) -> float:
        v = _mtime_for(
            kw.get("ename") or "",
            kw.get("instance") or {},
            exec_type=str(kw.get("exec_type") or "P"),
            exec_id=kw.get("exec_id"),
        )
        state["prp_before"] = v
        return v

    def prp_after(**kw: Any) -> float:
        ename = kw.get("ename") or ""
        instance = kw.get("instance") or {}
        et = str(kw.get("exec_type") or state.get("exec_type") or "P").strip().upper() or "P"
        eid = kw.get("exec_id") if kw.get("exec_id") is not None else state.get("exec_id")
        lock = _read_lock(ename, instance, exec_type=et, exec_id=eid)
        if lock:
            state["exec_id"] = lock.get("exec_id")
            state["upd_after"] = str(lock.get("upd") or "").strip().upper()
        return _mtime_for(ename, instance, exec_type=et, exec_id=state.get("exec_id"))

    def sdk(**kw: Any) -> dict:
        if sdk_exec is None:
            return {"ok": False, "path": "REPPREPDIRECT2", "reason": "sdk_hooks_missing"}
        return sdk_exec(**kw)

    def resolve_ename_types(*, ename: str, instance: dict, **_k: Any) -> list[dict]:
        if types_reader is None:
            return []
        rows = types_reader(ename=ename, instance=instance)
        return [r for r in (rows or []) if isinstance(r, dict)]

    out: dict[str, Any] = {
        "cred_present": cred_present,
        "sdk_exec": sdk,
        "read_upd": read_upd,
        "prp_mtime_before": prp_before,
        "prp_mtime_after": prp_after,
    }
    if types_reader is not None:
        out["resolve_ename_types"] = resolve_ename_types
    return out


def _norm_exec_type(raw: str | None) -> str:
    t = str(raw or "").strip().upper()
    if t in ("F", "FORM", "FORMS"):
        return "F"
    if t in ("R", "REPORT", "REPORTS"):
        return "R"
    if t in ("P", "PROCEDURE", "PROCEDURES", "PROC"):
        return "P"
    # Fail closed: never coerce unknown tokens via first letter (PIZZA -> P).
    return ""


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
    resolve_ename_types: Callable[..., list[dict]] | None = None,
    proc_type: str = "P",
    exec_type: str | None = None,
    form_via_sdk: bool = False,
) -> dict[str, Any]:
    """Named Priority prepare with UPD=N + .prp advanced gates.

    FR #5286 / #5933: untyped call is **procedure-only** (TYPE=P via
    REPPREPDIRECT2); missing/ambiguous/non-P refuse before SDK.

    FR #5946 / #6003: typed ``exec_type`` F|R|P prepares exactly that T$EXEC
    row: form → FORMPREPDRCT2; report/procedure → REPPREPDIRECT2. Never fall
    back to another type with the same ENAME. Default form prepare uses WINRUN
    (no priority-web-sdk); EFORM/EXEC SDK paths are opt-in only.
    """
    name = (ename or "").strip()
    raw_exec = str(exec_type).strip() if exec_type is not None else ""
    wanted = _norm_exec_type(raw_exec) if raw_exec else ""
    typed = wanted in ("F", "R", "P")
    if raw_exec and not typed:
        base_early: dict[str, Any] = {
            "ok": False,
            "ename": name,
            "exec": "REPPREPDIRECT2",
            "sql_faked": False,
            "prp_advanced": False,
            "reason": "bad_exec_type",
        }
        return base_early
    default_path = "FORMPREPDRCT2" if wanted == "F" else "REPPREPDIRECT2"
    base: dict[str, Any] = {
        "ok": False,
        "ename": name,
        "exec": default_path,
        "sql_faked": False,
        "prp_advanced": False,
    }
    if typed:
        base["exec_type"] = wanted
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

    chosen: dict | None = None
    # FR #5933 / #5946: resolve T$EXEC types before prep/.prp so form/report
    # refusals do not need a local prep folder (FR #5943 derivation machines vary).
    if resolve_ename_types is not None:
        try:
            rows = list(resolve_ename_types(ename=name, instance=inst) or [])
        except Exception as exc:  # noqa: BLE001
            reason = getattr(exc, "prepare_reason", None) or ""
            if reason == "sql_read_failed" or str(exc) == "sql_read_failed":
                base["reason"] = "sql_read_failed"
                return base
            rows = []
        rows = [r for r in rows if isinstance(r, dict)]
        types = sorted(
            {
                str(r.get("exec_type") or "").strip().upper()
                for r in rows
                if str(r.get("exec_type") or "").strip()
            }
        )
        if types:
            base["exec_types"] = ",".join(types)
        if not rows:
            base["reason"] = "ename_not_found"
            return base
        if typed:
            typed_rows = [
                r
                for r in rows
                if str(r.get("exec_type") or "").strip().upper() == wanted
            ]
            if not typed_rows:
                base["reason"] = "wrong_type"
                return base
            if len(typed_rows) > 1:
                base["reason"] = "ename_ambiguous"
                return base
            chosen = typed_rows[0]
        else:
            # Untyped: procedure-only (FR #5933).
            p_rows = [
                r
                for r in rows
                if str(r.get("exec_type") or "").strip().upper() == "P"
            ]
            if len(types) > 1 or len(p_rows) > 1:
                base["reason"] = "ename_ambiguous"
                return base
            if len(p_rows) == 0:
                base["reason"] = "not_type_p"
                return base
            chosen = p_rows[0]
            wanted = "P"
            base["exec_type"] = "P"

    if chosen is not None:
        exec_id = chosen.get("exec_id") or chosen.get("t$exec") or chosen.get("T$EXEC")
        try:
            exec_id_i = int(exec_id)
        except (TypeError, ValueError):
            exec_id_i = 0
        if exec_id_i:
            base["exec_id"] = exec_id_i
            base["prep_file"] = "d{0}.prp".format(exec_id_i)
        et = str(chosen.get("exec_type") or wanted or "P").strip().upper()
        wanted = et if et in ("F", "R", "P") else (wanted or "P")
        base["exec_type"] = wanted

    if not wanted:
        wanted = "P"
        base["exec_type"] = "P"

    resolved = resolve_prep_dir(inst)
    prep = str(resolved.get("path") or "").strip()
    base["prep_dir_tried"] = list(resolved.get("tried") or [])
    if resolved.get("derived_from"):
        base["prep_dir_derived_from"] = resolved.get("derived_from")
    if not prep:
        base["reason"] = "prep_dir_missing"
        base["prep_dir"] = ""
        base["prep_dir_source"] = ""
        base["prp_mtime_before"] = 0.0
        base["prp_mtime_after"] = 0.0
        return base
    # Stamp resolved path onto a copy so .prp hooks / mtime see the same folder.
    inst = dict(inst)
    inst["prepDir"] = prep
    base["prep_dir"] = prep
    base["prep_dir_source"] = str(resolved.get("source") or "")
    # FR #6008: name the artifact we will gate on (newest of .prp / .p).
    if base.get("exec_id") is not None:
        art, _mt = _prep_artifact_info(prep, base["exec_id"])
        base["prep_file"] = art.name

    # Form -> FORMPREPDRCT2; report/procedure -> REPPREPDIRECT2 (never swap).
    path = "FORMPREPDRCT2" if wanted == "F" else "REPPREPDIRECT2"
    base["exec"] = path
    form_prep = wanted == "F"
    # Capture .prp mtime BEFORE SDK so advance is meaningful.
    mtime_kw = {
        "ename": name,
        "instance": inst,
        "exec_type": wanted,
        "exec_id": base.get("exec_id"),
        "prep_file": base.get("prep_file"),
    }
    if callable(prp_mtime_before):
        before = float(prp_mtime_before(**mtime_kw))
    elif prp_mtime_before is None:
        before = 0.0
    else:
        before = float(prp_mtime_before)
    sdk_fn = sdk_exec or (lambda **_k: {"ok": False, "path": path})
    sdk = sdk_fn(
        path=path,
        ename=name,
        form_prep=form_prep,
        instance=inst,
        proc_type=wanted or proc_type,
        exec_type=wanted,
        exec_id=base.get("exec_id"),
        form_via_sdk=bool(form_via_sdk),
    )
    if not isinstance(sdk, dict) or not sdk.get("ok"):
        base["reason"] = "sdk_not_ok"
        if isinstance(sdk, dict) and sdk.get("reason"):
            base["sdk_reason"] = sdk.get("reason")
        return base
    upd_fn = read_upd or (lambda **_k: "")
    upd = str(
        upd_fn(
            ename=name,
            instance=inst,
            exec_type=wanted,
            exec_id=base.get("exec_id"),
        )
        or ""
    ).strip().upper()
    base["upd"] = upd
    after_fn = prp_mtime_after or (lambda **_k: before)
    after = float(after_fn(**mtime_kw))
    base["prp_mtime_before"] = before
    base["prp_mtime_after"] = after
    advanced = after > before
    base["prp_advanced"] = advanced
    if base.get("exec_id") is not None and prep:
        art, _mt = _prep_artifact_info(prep, base["exec_id"])
        base["prep_file"] = art.name
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
