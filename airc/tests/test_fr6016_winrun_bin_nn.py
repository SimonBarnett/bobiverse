"""FR #6016: derive WINRUN from per-install bin.NN, not only priorityRoot\\bin."""
from __future__ import annotations

import sys
from pathlib import Path

from repo_layout import ROOT

_SCRIPTS = ROOT / "airc" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import airc_console as ac  # noqa: E402


def _stub_run(seen):
    def fake_run(argv, **kw):
        seen["argv"] = list(argv)

        class P:
            returncode = 0
            stdout = ""
            stderr = ""

        return P()

    return fake_run


def _prepare_customers(root, prep, monkeypatch, seen, **inst_extra):
    monkeypatch.delenv("AIRC_PRIORITY_WINRUN", raising=False)
    monkeypatch.delenv("AIRC_PRIORITY_FORM_VIA_EFORM", raising=False)
    monkeypatch.delenv("AIRC_PRIORITY_FORM_VIA_EXEC", raising=False)
    inst = {
        "credentialTarget": "PriorityWeb/x",
        "company": "live1",
        "url": "https://example.invalid",
        "user": "tabula",
        "prepDir": str(prep),
    }
    inst.update(inst_extra)
    return ac._priority_prepare_exec(
        ename="CUSTOMERS",
        path="FORMPREPDRCT2",
        form_prep=True,
        instance=inst,
        cred_fetcher=lambda _t: "secret-placeholder-priority-pw",
        process_runner=_stub_run(seen),
    )


def test_fr6016_bin_nn_without_plain_bin(tmp_path, monkeypatch):
    """Acceptance: bin.95 + no winrunPath finds WINRUN (HR Smith layout)."""
    root = tmp_path / "priority"
    bin95 = root / "bin.95"
    bin95.mkdir(parents=True)
    winrun = bin95 / "WINRUN.EXE"
    winrun.write_text("stub", encoding="utf-8")
    prep = tmp_path / "prep"
    prep.mkdir()
    seen = {}
    out = _prepare_customers(root, prep, monkeypatch, seen, priorityRoot=str(root))
    assert out.get("ok") is True
    assert out.get("runner") == "winrun"
    argv0 = Path(seen["argv"][0])
    assert argv0.name.upper() == "WINRUN.EXE"
    assert argv0.parent.name.lower() == "bin.95"


def test_fr6016_prefers_highest_bin_nn_over_plain_bin(tmp_path, monkeypatch):
    """In-use versioned bin.NN wins over leftover priorityRoot\\bin."""
    root = tmp_path / "priority"
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "WINRUN.EXE").write_text("old", encoding="utf-8")
    (root / "bin.90").mkdir()
    (root / "bin.90" / "WINRUN.EXE").write_text("mid", encoding="utf-8")
    (root / "bin.95").mkdir()
    (root / "bin.95" / "WINRUN.EXE").write_text("new", encoding="utf-8")
    prep = tmp_path / "prep"
    prep.mkdir()
    seen = {}
    out = _prepare_customers(root, prep, monkeypatch, seen, priorityRoot=str(root))
    assert out.get("ok") is True
    assert Path(seen["argv"][0]).parent.name.lower() == "bin.95"


def test_fr6016_tabula_ini_derives_install_then_bin_nn(tmp_path, monkeypatch):
    """No priorityRoot: tabula.ini Priority Directory -> install root -> bin.NN."""
    root = tmp_path / "priority"
    prep = root / "system" / "prep"
    prep.mkdir(parents=True)
    bin95 = root / "bin.95"
    bin95.mkdir()
    (bin95 / "winrun.exe").write_text("stub", encoding="utf-8")
    windir = tmp_path / "Windows"
    windir.mkdir()
    (windir / "tabula.ini").write_text(
        "[Tabula]\nPriority Directory={0}\n".format(prep),
        encoding="utf-8",
    )
    monkeypatch.setenv("WINDIR", str(windir))
    monkeypatch.delenv("PRIORITY_ROOT", raising=False)
    monkeypatch.delenv("PRIORITY_HOME", raising=False)
    seen = {}
    out = _prepare_customers(root, prep, monkeypatch, seen)  # no priorityRoot
    assert out.get("ok") is True
    assert Path(seen["argv"][0]).parent.name.lower() == "bin.95"


def test_fr6016_winrun_path_override_still_wins(tmp_path, monkeypatch):
    root = tmp_path / "priority"
    (root / "bin.95").mkdir(parents=True)
    (root / "bin.95" / "WINRUN.EXE").write_text("derived", encoding="utf-8")
    other = tmp_path / "other"
    other.mkdir()
    override = other / "WINRUN.EXE"
    override.write_text("override", encoding="utf-8")
    prep = tmp_path / "prep"
    prep.mkdir()
    seen = {}
    out = _prepare_customers(
        root,
        prep,
        monkeypatch,
        seen,
        priorityRoot=str(root),
        winrunPath=str(override),
    )
    assert out.get("ok") is True
    assert Path(seen["argv"][0]).resolve() == override.resolve()
