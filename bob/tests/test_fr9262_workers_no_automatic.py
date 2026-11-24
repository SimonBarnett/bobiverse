"""FR #9262 / BOB-TRAY-UI-02: Workers dropdown excludes Automatic/auto id."""
from pathlib import Path

from repo_layout import REPO

TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
DOCS = REPO / "bob" / "docs" / "bob-tray-dialogs.md"
EVIDENCE = REPO / "bob" / "docs" / "bob-tray-ui-02-no-automatic-evidence.md"


def test_evidence_doc_pins_s1():
    text = EVIDENCE.read_text(encoding="utf-8")
    assert "BOB-TRAY-UI-02" in text or "9262" in text
    assert "Automatic" in text
    assert "Workers" in text


def test_seed_agent_choices_omits_auto():
    cs = TRAY.read_text(encoding="utf-8-sig")
    i = cs.find("void SeedAgentChoices")
    assert i > 0
    j = cs.find("void WorkerFaviconPath", i)
    seed = cs[i:j]
    assert 'AddAgentChoice(parent, "auto"' not in seed
    assert 'AddAgentChoice(parent, "grok"' in seed
    assert 'AddAgentChoice(parent, "cursor"' in seed
    assert "AddOpencodeTopLevelChoices" in seed


def test_apply_agent_list_fallback_omits_auto():
    cs = TRAY.read_text(encoding="utf-8-sig")
    i = cs.find("void ApplyAgentList")
    assert i > 0
    j = cs.find("static List<Dictionary<string, object>> ParseAgentRows", i)
    block = cs[i:j]
    assert 'AddAgentChoice(parent, "auto"' not in block
    assert 'id == "auto"' in block or 'Equals(id, "auto"' in block  # skip filter


def test_watch_workers_seed_omits_automatic():
    ps = WATCH.read_text(encoding="utf-8-sig")
    a = ps.find("Update-BobTrayWorkerAgentsMenu $miWorkers @(")
    assert a > 0
    b = ps.find(")", a)
    seed = ps[a:b]
    assert "id = 'auto'" not in seed
    assert "Automatic" not in seed
    assert "id = 'grok'" in seed


def test_get_worker_agent_choices_fallback_omits_auto():
    ps = WATCH.read_text(encoding="utf-8-sig")
    start = ps.find("function Get-BobTrayWorkerAgentChoices {")
    end = ps.find("function Update-BobTrayWorkerAgentsMenu {", start)
    fn = ps[start:end]
    assert "id = 'auto'" not in fn
    assert "label = 'Automatic'" not in fn


def test_docs_workers_line_omits_automatic():
    text = DOCS.read_text(encoding="utf-8")
    # Menu inventory line under BOB-06 / FR #8713 must not list Automatic.
    needle = "**Workers** ("
    i = text.find(needle)
    assert i > 0
    line_end = text.find("\n", i)
    line = text[i:line_end]
    assert "Automatic" not in line
    assert "Grok" in line
