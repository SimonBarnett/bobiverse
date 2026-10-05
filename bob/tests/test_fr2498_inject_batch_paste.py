"""FR #2498: inject_console must paste or batch — never drip per-char with sleeps."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import bob_worker as bw

SRC = Path(__file__).resolve().parents[1] / "scripts" / "bob_worker.py"


def test_inject_console_source_prefers_clipboard_and_no_per_char_sleep():
    src = SRC.read_text(encoding="utf-8")
    assert "FR #2498" in src
    assert "_clipboard_set_unicode" in src
    assert "_build_ctrl_v_records" in src
    assert "_write_console_all" in src
    tree = ast.parse(src)
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name in {"_write_console_all", "build_key_records", "_clipboard_set_unicode", "_build_ctrl_v_records"}:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    f = sub.func
                    if isinstance(f, ast.Attribute) and f.attr == "sleep":
                        raise AssertionError("sleep in " + node.name)
                    if isinstance(f, ast.Name) and f.id == "sleep":
                        raise AssertionError("sleep in " + node.name)
        if node.name == "inject_console":
            for loop in [n for n in ast.walk(node) if isinstance(n, ast.For)]:
                for sub in ast.walk(loop):
                    if isinstance(sub, ast.Call):
                        f = sub.func
                        if (isinstance(f, ast.Attribute) and f.attr == "sleep") or (isinstance(f, ast.Name) and f.id == "sleep"):
                            raise AssertionError("sleep inside for-loop in inject_console")


def test_build_key_records_two_events_per_char_intact():
    recs = bw.build_key_records("Az", user32=None)
    assert len(recs) == 4
    assert recs[0].Event.KeyEvent.uChar == "A"
    assert recs[2].Event.KeyEvent.uChar == "z"


def test_write_console_all_bounded_calls_on_partial_writes():
    recs = bw.build_key_records("abcd", user32=None)
    calls = []

    class K32:
        def WriteConsoleInputW(self, h, buf, n, written_ptr):
            written_ptr._obj.value = min(2, n)
            calls.append(n)
            return True

    import ctypes

    class Ptr:
        def __init__(self, obj):
            self._obj = obj
            self.contents = obj

    real = ctypes.byref
    ctypes.byref = lambda obj: Ptr(obj)  # type: ignore
    try:
        wintypes, _ = bw._win_structs()
        ok = bw._write_console_all(K32(), 1, recs, wintypes)
    finally:
        ctypes.byref = real
    assert ok is True
    assert len(calls) == 4
    assert calls[0] == 8


def test_inject_console_clipboard_path_few_writes(monkeypatch):
    writes = []
    monkeypatch.setattr(bw, "_clipboard_set_unicode", lambda text: True)
    monkeypatch.setattr(bw, "_build_ctrl_v_records", lambda: bw.build_enter_records())
    monkeypatch.setattr(bw, "_submit_gap_s", lambda default=0.20: 0.05)
    monkeypatch.setattr(bw.time, "sleep", lambda s: None)
    monkeypatch.setattr(bw, "_write_console_all", lambda k32, h, recs, wintypes: writes.append(len(recs)) or True)

    def make_k32():
        def CreateFileW(*a, **k):
            return 99
        def CloseHandle(h):
            return True
        return SimpleNamespace(CreateFileW=CreateFileW, CloseHandle=CloseHandle, WriteConsoleInputW=lambda *a, **k: True)

    monkeypatch.setattr(bw.ctypes, "WinDLL", lambda name, use_last_error=True: make_k32() if "kernel32" in name else SimpleNamespace())
    line = "FROM Jeeves #win-mpre8vi4u6u win-mpre8vi4u6u-7764: MRB SimonBarnett/bobiverse#2473 https://github.com/SimonBarnett/bobiverse/pull/2473"
    assert bw.inject_console(0, line) is True
    assert writes == [2, 2, 2]
    assert sum(writes) == 6
