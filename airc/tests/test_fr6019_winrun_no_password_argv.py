"""FR #6019: WINRUN form prepare must not put the Priority password on argv."""
from __future__ import annotations

import sys
from pathlib import Path

from repo_layout import ROOT

_WP = ROOT / "airc" / "priority-worker"
if str(_WP) not in sys.path:
    sys.path.insert(0, str(_WP))

import airc_console as ac  # noqa: E402

SECRET = "secret-placeholder-priority-pw"


def _inst(tmp_path):
    root = tmp_path / "priority"
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "WINRUN.EXE").write_text("stub", encoding="utf-8")
    prep = tmp_path / "prep"
    prep.mkdir()
    return {
        "credentialTarget": "PriorityWeb/x",
        "company": "live1",
        "user": "tabula",
        "prepDir": str(prep),
        "priorityRoot": str(root),
    }


def test_fr6019_default_winrun_argv_has_no_password(tmp_path, monkeypatch):
    """Acceptance: spawned argv never contains the CredMan password."""
    monkeypatch.delenv("AIRC_PRIORITY_FORM_VIA_EFORM", raising=False)
    monkeypatch.delenv("AIRC_PRIORITY_FORM_VIA_EXEC", raising=False)
    monkeypatch.delenv(ac._WINRUN_ARGV_OPTIN, raising=False)
    seen = {"n": 0, "argv": []}

    def fake_run(argv, **kw):
        seen["n"] += 1
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
        instance=_inst(tmp_path),
        cred_fetcher=lambda _t: SECRET,
        process_runner=fake_run,
    )
    assert SECRET not in seen["argv"]
    blob = str(out)
    assert SECRET not in blob
    assert out.get("ok") is False
    assert out.get("reason") == "winrun_password_argv"
    assert seen["n"] == 0


def test_fr6019_opt_in_still_keeps_password_out_of_payload(tmp_path, monkeypatch):
    """Opt-in argv password is documented risk; reply payload stays secret-free."""
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
        instance=_inst(tmp_path),
        cred_fetcher=lambda _t: SECRET,
        process_runner=fake_run,
    )
    assert out.get("ok") is True
    assert SECRET not in str(out)
    # Opt-in is the only path that may put the secret on WINRUN argv.
    assert SECRET in seen["argv"]
