"""FR #7130: Session 0 must not spawn WINACTIV; prepare-form uses Web SDK."""
from __future__ import annotations

import airc_console as ac


def test_parse_prepare_form_hyphen_uses_sdk_flag():
    p = ac.parse_priority_prepare_command(
        "id=aabb7130 PRIORITY prepare-form TRANSORDER_T instance=hrs-dev-live1"
    )
    assert p is not None
    assert p["name"] == "TRANSORDER_T"
    assert p["exec_type"] == "F"
    assert p["sdk_form"] == "1"
    assert p["instance"] == "hrs-dev-live1"


def test_parse_prepare_form_space_still_type_f():
    p = ac.parse_priority_prepare_command("PRIORITY prepare form ORDERS")
    assert p is not None
    assert p["exec_type"] == "F"
    assert p.get("sdk_form") is None


def test_session0_winrun_refuses_without_spawning(monkeypatch):
    monkeypatch.setattr(ac, "is_windows_session0", lambda: True)
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("must not spawn WINRUN in Session 0")

    out = ac._priority_winrun_formprep(
        ename="TRANSORDER_T",
        instance={
            "credentialTarget": "PriorityWeb/x",
            "company": "live1",
            "user": "tabula",
            "prepDir": "C:\\prep",
            "priorityRoot": "C:\\priority",
        },
        cred_fetcher=lambda _t: "x",
        process_runner=None,
        winrun_path=__file__,
    )
    assert out.get("ok") is False
    assert out.get("reason") == "session0_gui"
    assert called["n"] == 0


def test_prepare_form_hyphen_uses_eform_mjs(tmp_path, monkeypatch):
    mjs = tmp_path / "run-formprep-via-eform.mjs"
    mjs.write_text("/* stub */", encoding="utf-8")
    monkeypatch.setenv("AIRC_PRIORITY_FORMPREP_MJS", str(mjs))
    monkeypatch.setenv("AIRC_PRIORITY_NODE", "node")
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"] = list(argv)
        seen["env_pw"] = bool((kw.get("env") or {}).get("PRIORITY_SDK_PASSWORD"))

        class P:
            returncode = 0
            stdout = '{"ok":true,"ended":true}'
            stderr = ""

        return P()

    monkeypatch.setattr(ac.shutil, "which", lambda _n: "C:\\node.exe")
    out = ac._priority_prepare_exec(
        ename="TRANSORDER_T",
        path="FORMPREPDRCT2",
        form_prep=True,
        form_via_sdk=True,
        instance={
            "credentialTarget": "PriorityWeb/x",
            "company": "live1",
            "user": "tabula",
            "url": "https://priority.example.invalid",
        },
        cred_fetcher=lambda _t: "secret-placeholder-priority-pw",
        node_runner=fake_run,
    )
    assert out.get("ok") is True
    assert out.get("runner") == "sdk-eform"
    assert "run-formprep-via-eform.mjs" in " ".join(seen["argv"])
    assert "WINACTIV" not in seen["argv"]
    assert seen["env_pw"] is True
    assert "TRANSORDER_T" in seen["argv"]
