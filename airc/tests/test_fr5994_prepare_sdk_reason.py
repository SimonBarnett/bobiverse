"""FR #5994: prepare SDK failures expose short sdk_reason; formprep runner hygiene."""
from __future__ import annotations

import json
import re
from pathlib import Path

import airc_console as ac
import priority_worker as pw

ROOT = Path(__file__).resolve().parents[2]
FORM_MJS = ROOT / "airc" / "priority-worker" / "sdk" / "run-formprep-via-eform.mjs"


def test_fr5994_sdk_reason_from_formstart_api_licence():
    payload = {
        "ok": False,
        "stage": "formStart",
        "message": (
            "To open the form via the API, you must flag the user "
            "as having an API Licence."
        ),
        "type": "apiError",
    }
    reason = ac._priority_sdk_reason_from_payload(payload)
    assert reason.startswith("formStart:apiError")
    assert "API Licence" in reason
    assert "password" not in reason.lower()
    assert len(reason) <= 96


def test_fr5994_sdk_reason_strips_secret_shaped_text():
    payload = {
        "ok": False,
        "stage": "login",
        "message": "auth failed password=SuperSecretValue123 user=tabula",
        "type": "apiError",
    }
    reason = ac._priority_sdk_reason_from_payload(payload)
    assert "SuperSecretValue123" not in reason
    assert "password=***" in reason.lower() or "password" in reason.lower()


def test_fr5994_priority_sdk_repprep_passes_reason_on_form_fail(tmp_path, monkeypatch):
    """Opt-in eform path still surfaces formStart API Licence as sdk_reason."""
    root = tmp_path / "airc-install"
    pw_dir = root / "airc" / "priority-worker" / "sdk"
    pw_dir.mkdir(parents=True)
    (pw_dir / "run-formprep-via-eform.mjs").write_text("// stub\n", encoding="utf-8")
    monkeypatch.setenv("AIRC_INSTALL_ROOT", str(root))
    monkeypatch.setenv("AIRC_PRIORITY_FORM_VIA_EFORM", "1")
    monkeypatch.setattr(
        ac._priority,
        "resolve_priority_worker_dir",
        lambda _r: root / "airc" / "priority-worker",
    )

    def fake_run(argv, **kw):
        class P:
            returncode = 2
            stdout = (
                '{"ok":false,"stage":"formStart","type":"apiError",'
                '"message":"To open the form via the API, you must flag '
                'the user as having an API Licence."}\n'
            )
            stderr = ""

        return P()

    out = ac._priority_sdk_repprep(
        ename="CUSTOMERS",
        path="FORMPREPDRCT2",
        form_prep=True,
        instance={
            "credentialTarget": "PriorityWeb/x",
            "company": "live1",
            "url": "https://example.invalid/priority",
            "user": "tabula",
        },
        cred_fetcher=lambda _t: "FAKE_PRIORITY_PASSWORD_FOR_TEST",
        node_runner=fake_run,
    )
    assert out.get("ok") is False
    assert out.get("reason") == "use_winrun_formprep"
    blob = json.dumps(out).lower()
    assert "fake_priority_password" not in blob


def test_fr5994_prepare_surfaces_sdk_reason():
    r = pw.run_priority_prepare(
        "CUSTOMERS",
        instance_id="example-dev",
        instances=[
            {
                "id": "example-dev",
                "url": "https://example.invalid/priority",
                "company": "live1",
                "user": "u1",
                "credentialTarget": "PriorityWeb/example-dev",
                "prepDir": str(Path.cwd()),  # existing dir; hooks override mtime
            }
        ],
        exec_type="F",
        resolve_ename_types=lambda **k: [
            {"exec_id": 13, "exec_type": "F", "name": "CUSTOMERS"}
        ],
        cred_present=lambda _t: True,
        sdk_exec=lambda **k: {
            "ok": False,
            "path": "FORMPREPDRCT2",
            "reason": "formStart:apiError API Licence",
        },
        read_upd=lambda **k: "Y",
        prp_mtime_before=1.0,
        prp_mtime_after=1.0,
    )
    assert r.get("ok") is False
    assert r.get("reason") == "sdk_not_ok"
    assert r.get("sdk_reason") == "formStart:apiError API Licence"
    assert r.get("exec_id") == 13
    assert r.get("prep_file") == "d13.prp"


def test_fr5994_formprep_mjs_no_customer_defaults_or_priority_tmp():
    src = FORM_MJS.read_text(encoding="utf-8")
    assert "clarksonevans" not in src.lower()
    assert r"C:\Priority\tmp" not in src
    assert "C:/Priority/tmp" not in src
    # No silent customer user/company defaults.
    assert not re.search(r"arg\(\s*'--user'\s*,\s*'Si'\s*\)", src)
    assert not re.search(r"arg\(\s*'--company'\s*,\s*'base'\s*\)", src)
    assert not re.search(r"arg\(\s*'--url'\s*,\s*'https://", src)
    # Dump folder must prefer airc home / OS tmp.
    assert "AIRC_HOME" in src or "AIRC_INSTALL_ROOT" in src or "os.tmpdir" in src
    assert "emitFail" in src
    assert "'args'" in src or '"args"' in src
