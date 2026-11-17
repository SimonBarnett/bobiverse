"""FR #8142: FORM-PREPARE menu naming, older-host EXECPREPLOCK schema, FORMCLTRIGTEXT workflow."""
from __future__ import annotations

import airc_console as ac
import priority_wcf as wcf

INST = {
    "id": "example-dev",
    "url": "https://prioritydev.example.invalid",
    "company": "live1",
    "user": "api-user",
    "credentialTarget": "PriorityWeb/example-dev",
    "sqlServer": ".\\PRI",
    "systemDb": "system",
    "prepDir": "E:\\priority\\system\\prep",
}


def test_fr8142_ename_rows_read_texec_only_not_execpreplock(monkeypatch):
    """Type resolution must not JOIN EXECPREPLOCK (older hosts lack UPD/ENAME)."""
    class _Proc:
        def __init__(self):
            self.stdout = "TRANSORDER_T|595|F\n"
            self.stderr = ""
            self.returncode = 0

    captured = {}

    def fake_run(argv, **kw):
        captured["argv"] = list(argv)
        return _Proc()

    rows = ac._priority_sqlcmd_ename_rows(
        ename="TRANSORDER_T", instance=INST, runner=fake_run
    )
    argv = " ".join(captured["argv"])
    q = str(captured["argv"][captured["argv"].index("-Q") + 1])
    assert "EXECPREPLOCK" not in q
    assert "LEFT JOIN" not in q
    assert "ISNULL" not in q
    assert "L.UPD" not in q
    assert "T$EXEC" in q
    assert len(rows) == 1
    assert rows[0]["exec_id"] == 595
    assert rows[0]["exec_type"] == "F"
    assert rows[0]["name"] == "TRANSORDER_T"


def test_fr8142_formprepare_menu_label_refused_unscoped():
    """FORM-PREPARE / FORM PREPARE (menu label) normalize to FORMPREP and refuse."""
    for key in ("ename", "name"):
        for label in ("FORM-PREPARE", "FORM PREPARE", "FORM_PREPARE", "FORMPREP"):
            assert wcf.use_prepare_verb("ProcStart", {key: label}) is True, (key, label)
    assert wcf.use_prepare_verb("ProcStart", {"ename": "TRANSORDER_T"}) is False
    assert wcf.use_prepare_verb("ProcStart", {"name": "ORDERS"}) is False


def test_fr8142_docs_and_skill_name_formprepare_and_formcltrigtext():
    import re

    from repo_layout import ROOT

    doc = (ROOT / "airc" / "docs" / "airc-priority-client.md").read_text(encoding="utf-8")
    skill = (
        ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-commands" / "SKILL.md"
    ).read_text(encoding="utf-8")
    rc = (ROOT / "airc" / "docs" / "airc-remote-control.md").read_text(encoding="utf-8")
    for text in (doc, skill):
        assert "FORM-PREPARE" in text
        assert "FORMCLTRIGTEXT" in text
        assert "FORMPREPDRCT2" in text
        assert "TRANSORDER_T" in text
    assert "FORM-PREPARE" in rc
    assert "FORMCLTRIGTEXT" in rc
    # FR #3935: the skill book stays em-dash-free (the existing prepare-gates
    # test already pins this; keep it here for the new prose we added).
    assert re.search(r"[\u2014\u2013]", skill) is None
