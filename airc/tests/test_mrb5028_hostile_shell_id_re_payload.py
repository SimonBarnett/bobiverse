"""MRB #5028 hostile pins: FR #5027 _SHELL_ID_RE out/err payload + inflight track."""
from __future__ import annotations

import re
from pathlib import Path

import airc_console_service as svc


def _svc(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "x-server-pass")
    args = svc.build_arg_parser().parse_args(
        ["--machine", "tm", "--home", str(tmp_path), "--shop-mode", "registered", "--operators", "op"]
    )
    return svc.AircConsoleService(args)


def test_mrb5028_on_console_out_status_payload_sets_inflight(tmp_path, monkeypatch):
    """Vision S3 / FR #2612: out id= seq=N STATUS ... must note_shell_inflight."""
    s = _svc(tmp_path, monkeypatch)
    monkeypatch.setattr(svc, "FLOOD_S", 0.0)
    s.sock = type("S", (), {"sendall": staticmethod(lambda data: None)})()
    line = "out id=cf38f565 seq=1 STATUS machine=tm airc=Running bob=1"
    s._on_console_out("bob-tm", line)
    assert s.shell_inflight().get("bob-tm") == "cf38f565"


def test_mrb5028_broken_outer_end_anchor_rejects_payload():
    """Regression shape from FR #5003: \\s*$ outside alternation breaks payload lines."""
    broken = re.compile(
        r"^(?:(?:out|err)\s+id=([0-9a-f]+)\s+seq=\d+|DONE\s+(?:id=([0-9a-f]+)\s+)?exit=-?\d+(?:\s+\S+)*)\s*$",
        re.IGNORECASE,
    )
    assert broken.match("out id=cf38f565 seq=1 LINE1") is None
    assert svc._SHELL_ID_RE.match("out id=cf38f565 seq=1 LINE1") is not None


def test_mrb5028_source_done_branch_end_anchored_only():
    src = Path(svc.__file__).read_text(encoding="utf-8")
    assert "FR #5027" in src
    m = re.search(r'_SHELL_ID_RE = re\.compile\(\s*(?:#[^\n]*\n\s*)*r"([^"]+)"', src)
    assert m, "_SHELL_ID_RE pattern literal missing"
    pat = m.group(1)
    assert pat.endswith(r"(?:\s+\S+)*\s*$)"), pat
    # Must not re-introduce outer \\s*$ after the whole alternation.
    assert not re.search(r"\)\\s\*\$\"?\s*,\s*re\.IGNORECASE", src)
