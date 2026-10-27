"""FR #5027: _SHELL_ID_RE must match out/err lines that carry payload text after seq=N."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MOD_PATH = REPO / "airc" / "scripts" / "airc_console_service.py"


def _load():
    spec = importlib.util.spec_from_file_location("airc_console_service", MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_fr5027_shell_id_re_matches_out_with_payload_text():
    mod = _load()
    m = mod._SHELL_ID_RE.match("out id=cf38f565 seq=1 LINE1")
    assert m is not None, "out/err branch must allow trailing payload text (FR #5027)"
    assert (m.group(1) or "").lower() == "cf38f565"


def test_fr5027_shell_id_re_matches_err_with_payload_text():
    mod = _load()
    m = mod._SHELL_ID_RE.match("err id=deadbeef seq=2 boom")
    assert m is not None
    assert (m.group(1) or "").lower() == "deadbeef"


def test_fr5027_shell_id_re_still_matches_done_variants():
    mod = _load()
    rx = mod._SHELL_ID_RE
    assert rx.match("DONE id=cf38f565 exit=0") is not None
    assert rx.match("DONE exit=0") is not None
    assert rx.match("DONE id=cf38f565 exit=0 bytes=12 sha256=abc via=dcc") is not None


def test_fr5027_shell_id_re_source_anchors_done_branch():
    t = MOD_PATH.read_text(encoding="utf-8")
    m = re.search(r'_SHELL_ID_RE = re\.compile\(\s*(?:#[^\n]*\n\s*)*r"([^"]+)"', t)
    assert m, "_SHELL_ID_RE pattern literal missing"
    pat = m.group(1)
    assert pat.endswith(r"(?:\s+\S+)*\s*$)"), pat
    assert "FR #5027" in t
