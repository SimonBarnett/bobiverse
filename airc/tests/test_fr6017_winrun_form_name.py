"""FR #6017: WINRUN form prepare must pass the named ENAME (not all pending)."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from repo_layout import ROOT

_WP = ROOT / "airc" / "priority-worker"
if str(_WP) not in sys.path:
    sys.path.insert(0, str(_WP))

import airc_console as ac  # noqa: E402
import priority_worker as pw  # noqa: E402


def _winrun_tree(tmp_path):
    root = tmp_path / "priority"
    (root / "bin").mkdir(parents=True)
    winrun = root / "bin" / "WINRUN.EXE"
    winrun.write_text("stub", encoding="utf-8")
    prep = tmp_path / "prep"
    prep.mkdir()
    return root, winrun, prep


def test_fr6017_winrun_argv_includes_ename(tmp_path, monkeypatch):
    """Acceptance: WINRUN command carries the form ENAME after FORMPREP."""
    root, _winrun, prep = _winrun_tree(tmp_path)
    monkeypatch.delenv("AIRC_PRIORITY_FORM_VIA_EFORM", raising=False)
    monkeypatch.delenv("AIRC_PRIORITY_FORM_VIA_EXEC", raising=False)
    monkeypatch.setenv(ac._WINRUN_ARGV_OPTIN, "1")
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"] = list(argv)

        class P:
            returncode = 0
            stdout = ""
            stderr = ""

        return P()

    out = ac._priority_prepare_exec(
        ename="CUSTOMERS",
        path="FORMPREPDRCT2",
        form_prep=True,
        instance={
            "credentialTarget": "PriorityWeb/x",
            "company": "live1",
            "user": "tabula",
            "prepDir": str(prep),
            "priorityRoot": str(root),
        },
        cred_fetcher=lambda _t: "secret-placeholder-priority-pw",
        process_runner=fake_run,
    )
    assert out.get("ok") is True
    argv = seen["argv"]
    assert argv[argv.index("FORMPREP") + 1] == "CUSTOMERS"
    assert "ORDERS" not in argv


def test_fr6017_empty_ename_refuses_unscoped_formprep(tmp_path, monkeypatch):
    """No named form: refuse rather than WINRUN FORMPREP with no target."""
    root, _winrun, prep = _winrun_tree(tmp_path)
    monkeypatch.delenv("AIRC_PRIORITY_FORM_VIA_EFORM", raising=False)
    monkeypatch.delenv("AIRC_PRIORITY_FORM_VIA_EXEC", raising=False)
    monkeypatch.setenv(ac._WINRUN_ARGV_OPTIN, "1")
    called = {"n": 0}

    def fake_run(argv, **kw):
        called["n"] += 1

        class P:
            returncode = 0

        return P()

    out = ac._priority_winrun_formprep(
        ename="  ",
        instance={
            "credentialTarget": "PriorityWeb/x",
            "company": "live1",
            "user": "tabula",
            "prepDir": str(prep),
            "priorityRoot": str(root),
        },
        cred_fetcher=lambda _t: "secret-placeholder-priority-pw",
        process_runner=fake_run,
    )
    assert out.get("ok") is False
    assert out.get("reason") == "ename_missing"
    assert called["n"] == 0


def test_fr6017_two_forms_only_named_prp_rewritten(tmp_path, monkeypatch):
    """Two pending forms: prepare form CUSTOMERS must not rewrite ORDERS files."""
    root, _winrun, prep = _winrun_tree(tmp_path)
    customers = prep / "d13.prp"
    orders = prep / "d99.prp"
    customers.write_text("old-c", encoding="utf-8")
    orders.write_text("old-o", encoding="utf-8")
    # FR #6966: Windows can keep the same st_mtime within one second under suite
    # load; pin an older before-mtime so the prepare gate sees a real advance.
    old_m = time.time() - 60
    os.utime(customers, (old_m, old_m))
    os.utime(orders, (old_m, old_m))
    monkeypatch.delenv("AIRC_PRIORITY_FORM_VIA_EFORM", raising=False)
    monkeypatch.delenv("AIRC_PRIORITY_FORM_VIA_EXEC", raising=False)
    monkeypatch.setenv(ac._WINRUN_ARGV_OPTIN, "1")

    def fake_run(argv, **kw):
        # Unscoped FORMPREP would rewrite every pending form; named ENAME must not.
        if "FORMPREP" in argv and "CUSTOMERS" in argv and "ORDERS" not in argv:
            customers.write_text("new-c", encoding="utf-8")
            now = time.time()
            os.utime(customers, (now, now))
        else:
            customers.write_text("new-c", encoding="utf-8")
            orders.write_text("new-o", encoding="utf-8")
            now = time.time()
            os.utime(customers, (now, now))
            os.utime(orders, (now, now))

        class P:
            returncode = 0
            stdout = ""
            stderr = ""

        return P()

    inst = {
        "id": "hrs-dev-live1",
        "credentialTarget": "PriorityWeb/x",
        "company": "live1",
        "user": "tabula",
        "prepDir": str(prep),
        "priorityRoot": str(root),
    }

    def types(**kw):
        # SQL lookup is per ENAME; ORDERS is a sibling pending form on disk only.
        return [{"name": "CUSTOMERS", "exec_id": 13, "exec_type": "F", "upd": "Y"}]

    r = pw.run_priority_prepare(
        "CUSTOMERS",
        instance_id="hrs-dev-live1",
        instances=[inst],
        exec_type="F",
        cred_present=lambda _t: True,
        sdk_exec=lambda **kw: ac._priority_prepare_exec(
            process_runner=fake_run,
            cred_fetcher=lambda _t: "secret-placeholder-priority-pw",
            **kw,
        ),
        read_upd=lambda **kw: "N",
        prp_mtime_before=lambda **kw: customers.stat().st_mtime
        if int(kw.get("exec_id") or 0) == 13
        else orders.stat().st_mtime,
        prp_mtime_after=lambda **kw: customers.stat().st_mtime
        if int(kw.get("exec_id") or 0) == 13
        else orders.stat().st_mtime,
        resolve_ename_types=types,
    )
    assert r.get("ok") is True, r
    assert r.get("reason") != "prp_unchanged", r
    assert customers.read_text(encoding="utf-8") == "new-c"
    assert orders.read_text(encoding="utf-8") == "old-o"
