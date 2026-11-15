"""FR #7421: bob_downloads_assets.main ends CLI JSON with a real newline."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from repo_layout import REPO

SCRIPT = REPO / "common" / "scripts" / "bob_downloads_assets.py"


def _load():
    spec = importlib.util.spec_from_file_location("bob_downloads_assets", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_fr7421_source_uses_real_newline_escape():
    src = SCRIPT.read_text(encoding="utf-8")
    # Bug was a double-escaped newline: source contained "\\n" (backslash + n).
    # Fixed form is a single escape: "\n" (real newline character when evaluated).
    assert 'endswith("\\n")' in src
    assert 'endswith("\\\\n")' not in src
    write_line = [ln for ln in src.splitlines() if "sys.stdout.write(text +" in ln]
    assert write_line, "stdout.write line missing"
    assert '"\\n"' in write_line[0]
    assert '"\\\\n"' not in write_line[0]


def test_fr7421_main_appends_real_newline(tmp_path, capsys):
    payload = {
        "tag_name": "v1.0.0",
        "assets": [
            {"name": "bob-1.0.0.msi"},
            {"name": "jeeves-1.0.0.msi"},
            {"name": "airc-1.0.0.msi"},
        ],
    }
    jf = tmp_path / "rel.json"
    jf.write_text(json.dumps(payload), encoding="utf-8")
    mod = _load()
    rc = mod.main(["--json-file", str(jf)])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.endswith("\n"), repr(out[-20:])
    assert "\\n" not in out.rstrip("\n")
    json.loads(out)
