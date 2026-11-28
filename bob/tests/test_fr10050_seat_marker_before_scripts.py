"""FR #10050: a starting seat writes a marker before shipped-scripts."""
from repo_layout import ROOT

SRC = (ROOT / "bob" / "scripts" / "bob_worker.py").read_text(encoding="utf-8")


def test_fr10050_marker_precedes_shipped_scripts():
    main = SRC.index("def main(")
    body = SRC[main:]
    marker = body.index("phase=before-shipped-scripts")
    prefer = body.index("prefer_shipped_scripts_on_sys_path")
    assert marker < prefer
    assert "FR #10050" in body[:prefer]
