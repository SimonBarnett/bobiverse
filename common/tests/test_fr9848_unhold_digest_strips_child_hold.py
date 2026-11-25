# -*- coding: utf-8 -*-
"""FR #9848: unhold parent fr-digest strips hold from Depends-on children."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import gitclaim

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "common" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import fr_digest_gate  # noqa: E402

REPO = "SimonBarnett/bobiverse"


def _row(num: int, **kw) -> dict:
    r = {
        "repo": REPO,
        "task": "FR",
        "id": f"#{num}",
        "seq": num,
        "ts": f"2026-11-24T10:00:{num % 60:02d}Z",
        "line": f"FR {REPO}#{num}",
        "url": f"https://github.com/{REPO}/issues/{num}",
        "title": f"FR {num}",
        "state": "open",
        "body": "Depends-on: (none)\n",
        "event": "issues",
        "labels": [],
    }
    r.update(kw)
    return r


def test_fr9848_docs_cast_iron():
    doc = (ROOT / "jeeves" / "docs" / "fr-digest-vs-hold-vs-depends-on.md").read_text(
        encoding="utf-8"
    )
    assert "9848" in doc
    assert "digest-children" in doc.lower() or "child hold" in doc.lower()
    gate = (SCRIPTS / "fr_digest_gate.py").read_text(encoding="utf-8")
    assert "9848" in gate
    assert "strip_hold" in gate or "unhold" in gate.lower()


def test_fr9848_strip_hold_from_non_digest_children():
    doc = {
        "v": 1,
        "unaccepted": [
            _row(
                9148,
                title="Digest: Jeeves agent skills",
                labels=["feature-request", "fr-digest", "digest"],
                body="Kind: fr-digest\n",
            ),
            _row(
                8775,
                title="leaflet",
                body="Depends-on: #9148\n",
                labels=["feature-request", "hold", "via-intake"],
            ),
            _row(
                8776,
                title="leaflet2",
                body="Depends-on: #9148\n",
                labels=["feature-request", "on-hold"],
            ),
            _row(
                9999,
                title="unrelated held",
                body="Depends-on: (none)\n",
                labels=["feature-request", "hold"],
            ),
        ],
        "accepted": [],
        "done": [],
    }
    removed: list[tuple[str, int, str]] = []

    def _rm(repo: str, num: int, label: str) -> bool:
        removed.append((repo, num, label))
        return True

    actions = gitclaim.strip_hold_from_digest_children(
        None,
        doc,
        REPO,
        "9148",
        remove_github_label=_rm,
    )
    assert actions
    assert any("8775" in a for a in actions)
    assert any("8776" in a for a in actions)
    child75 = next(r for r in doc["unaccepted"] if str(r["id"]).lstrip("#") == "8775")
    child76 = next(r for r in doc["unaccepted"] if str(r["id"]).lstrip("#") == "8776")
    unrelated = next(r for r in doc["unaccepted"] if str(r["id"]).lstrip("#") == "9999")
    assert "hold" not in {x.lower() for x in child75["labels"]}
    assert "on-hold" not in {x.lower() for x in child76["labels"]}
    assert "hold" in {x.lower() for x in unrelated["labels"]}
    assert (REPO, 8775, "hold") in removed
    assert (REPO, 8776, "on-hold") in removed


def test_fr9848_nested_digest_child_keeps_hold():
    """FR #9860: nested digest children are not auto-unheld with the parent."""
    doc = {
        "v": 1,
        "unaccepted": [
            _row(
                100,
                title="Digest: parent",
                labels=["fr-digest", "digest"],
                body="Kind: fr-digest\n",
            ),
            _row(
                101,
                title="Digest: nested phase",
                labels=["fr-digest", "digest", "hold"],
                body="Kind: fr-digest\nDepends-on: #100\n",
            ),
            _row(
                102,
                title="ordinary child",
                labels=["feature-request", "hold"],
                body="Depends-on: #100\n",
            ),
        ],
        "accepted": [],
        "done": [],
    }
    actions = gitclaim.strip_hold_from_digest_children(None, doc, REPO, "100")
    nested = next(r for r in doc["unaccepted"] if str(r["id"]).lstrip("#") == "101")
    ordinary = next(r for r in doc["unaccepted"] if str(r["id"]).lstrip("#") == "102")
    assert "hold" in {x.lower() for x in nested["labels"]}
    assert "hold" not in {x.lower() for x in ordinary["labels"]}
    assert any("102" in a for a in actions)
    assert not any("101" in a for a in actions)


def test_fr9848_label_mutation_unhold_parent_strips_children(tmp_path: Path):
    home = tmp_path
    digest = _row(
        9148,
        title="Digest: skills",
        labels=["feature-request", "fr-digest", "digest", "hold"],
        body="Kind: fr-digest\n",
    )
    child = _row(
        8775,
        title="leaflet",
        body="Depends-on: #9148\n",
        labels=["feature-request", "hold"],
    )
    doc = {"v": 1, "unaccepted": [digest, child], "accepted": [], "done": []}
    gitclaim._write_queue(gitclaim.queue_path(home), doc)

    removed: list[tuple[str, int, str]] = []

    def _rm(repo: str, num: int, label: str) -> bool:
        removed.append((repo, num, label))
        return True

    # Inject remover for this process.
    gitclaim._FR9848_REMOVE_LABEL = _rm  # type: ignore[attr-defined]
    try:
        claim = SimpleNamespace(
            repo=REPO,
            task="FR",
            id="9148",
            action="unlabeled",
            event="issues",
            labels=["feature-request", "fr-digest", "digest"],  # hold gone
            title=digest["title"],
            body=digest["body"],
            state="open",
            harvest_lesson=False,
            opened_by="",
            line=f"FR {REPO}#9148",
            refs=(),
        )
        with gitclaim._lock(home):
            q = gitclaim._load_queue_unlocked(home)
            ch = gitclaim._apply_label_mutation(q, claim, home=home)
            gitclaim._write_queue(gitclaim.queue_path(home), q)
        assert ch in ("updated", "added", "noop", "removed")
        q2 = gitclaim.load_queue(home)
        child2 = next(
            r
            for r in (q2.get("unaccepted") or [])
            if str(r.get("id") or "").lstrip("#") == "8775"
        )
        assert "hold" not in {str(x).lower() for x in (child2.get("labels") or [])}
        assert (REPO, 8775, "hold") in removed
        notes = q2.get("stand_down") or []
        assert any("9848" in str(n.get("text") or "") for n in notes if isinstance(n, dict))
    finally:
        gitclaim._FR9848_REMOVE_LABEL = None  # type: ignore[attr-defined]


def test_fr9848_fail_when_parent_unheld_kids_stay_held():
    """Document the starvation mode without the strip helper."""
    child_labels = ["feature-request", "hold"]
    assert gitclaim.fr_hold_reason(title="x", body="", labels=child_labels)
    stripped = fr_digest_gate.strip_hold_labels(child_labels)
    assert "hold" not in {x.lower() for x in stripped}
    assert gitclaim.fr_hold_reason(title="x", body="", labels=stripped) is None


def test_fr9848_should_strip_predicate():
    ordinary = _row(1, labels=["hold"], body="Depends-on: #9\n")
    nested = _row(
        2,
        labels=["fr-digest", "hold"],
        body="Kind: fr-digest\nDepends-on: #9\n",
    )
    assert fr_digest_gate.should_strip_child_hold_on_parent_unhold(ordinary) is True
    assert fr_digest_gate.should_strip_child_hold_on_parent_unhold(nested) is False
