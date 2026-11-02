"""FR #6008: report prepare gates on newest of .p / .prp (reports rewrite .p)."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from repo_layout import ROOT

_WP = ROOT / "airc" / "priority-worker"
if str(_WP) not in sys.path:
    sys.path.insert(0, str(_WP))

import priority_worker as pw  # noqa: E402

INST = {
    "id": "hrs-dev-live1",
    "url": "https://prioritydev.example.invalid",
    "company": "live1",
    "user": "tabula",
    "credentialTarget": "PriorityWeb/hrs-dev-live1",
    "sqlServer": ".\\PRI",
    "systemDb": "system",
}


def test_fr6008_prep_artifact_info_picks_newest_p_over_stale_prp(tmp_path):
    prep = tmp_path / "prep"
    prep.mkdir()
    prp = prep / "d296.prp"
    prp.write_text("stale-prp", encoding="utf-8")
    old = time.time() - (86400 * 365 * 5)
    os.utime(prp, (old, old))
    pfile = prep / "d296.p"
    pfile.write_text("fresh-p", encoding="utf-8")
    fresh = time.time() - 10
    os.utime(pfile, (fresh, fresh))

    art, mt = pw._prep_artifact_info(str(prep), 296)
    assert art.name == "d296.p"
    assert mt is not None
    assert mt >= fresh - 1


def test_fr6008_report_ok_when_only_p_advances(tmp_path):
    """Acceptance: stale .prp + advancing .p => prepared / ok:true for TYPE=R."""
    prep = tmp_path / "prep"
    prep.mkdir()
    prp = prep / "d296.prp"
    prp.write_text("stale-prp", encoding="utf-8")
    old = time.time() - (86400 * 365 * 5)
    os.utime(prp, (old, old))
    pfile = prep / "d296.p"
    pfile.write_text("before", encoding="utf-8")
    before_m = time.time() - 120
    os.utime(pfile, (before_m, before_m))

    inst = dict(INST)
    inst["prepDir"] = str(prep)

    def sdk(**kw):
        pfile.write_text("after-rewrite", encoding="utf-8")
        now = time.time()
        os.utime(pfile, (now, now))
        # Leave .prp untouched (HR Smith report behaviour).
        return {"ok": True, "path": kw.get("path") or "REPPREPDIRECT2"}

    hooks = pw.build_default_prepare_hooks(
        cred_fetcher=lambda _t: "secret-placeholder-priority-pw",
        lock_reader=lambda **_k: {
            "exec_id": 296,
            "exec_type": "R",
            "upd": "N",
        },
        types_reader=lambda **_k: [
            {"name": "CUSTOMERS", "exec_id": 296, "exec_type": "R", "upd": "Y"}
        ],
        sdk_exec=sdk,
    )
    r = pw.run_priority_prepare(
        "CUSTOMERS",
        instance_id="hrs-dev-live1",
        instances=[inst],
        exec_type="R",
        **hooks,
    )
    assert r.get("ok") is True, r
    assert r.get("reason") == "prepared"
    assert r.get("exec_type") == "R"
    assert int(r.get("exec_id")) == 296
    assert r.get("prep_file") == "d296.p"
    assert r.get("prp_advanced") is True
    assert float(r.get("prp_mtime_after") or 0) > float(r.get("prp_mtime_before") or 0)


def test_fr6008_procedure_still_gates_on_prp_when_only_prp_exists(tmp_path):
    prep = tmp_path / "prep"
    prep.mkdir()
    prp = prep / "d21848.prp"
    prp.write_text("before", encoding="utf-8")
    before_m = time.time() - 60
    os.utime(prp, (before_m, before_m))

    inst = dict(INST)
    inst["prepDir"] = str(prep)

    def sdk(**kw):
        prp.write_text("after", encoding="utf-8")
        now = time.time()
        os.utime(prp, (now, now))
        return {"ok": True, "path": "REPPREPDIRECT2"}

    hooks = pw.build_default_prepare_hooks(
        cred_fetcher=lambda _t: "secret-placeholder-priority-pw",
        lock_reader=lambda **_k: {
            "exec_id": 21848,
            "exec_type": "P",
            "upd": "N",
        },
        types_reader=lambda **_k: [
            {"name": "WWWSHOWCUST", "exec_id": 21848, "exec_type": "P", "upd": "Y"}
        ],
        sdk_exec=sdk,
    )
    r = pw.run_priority_prepare(
        "WWWSHOWCUST",
        instance_id="hrs-dev-live1",
        instances=[inst],
        exec_type="P",
        **hooks,
    )
    assert r.get("ok") is True, r
    assert r.get("prep_file") == "d21848.prp"
    assert r.get("reason") == "prepared"
