"""Bounded, redacted worker transcripts without changing a child's console handles."""
from __future__ import annotations

from collections import deque
import ctypes
import json
import os
from pathlib import Path
import sys
import threading
import time

try:
    from crash_report import redact
except ModuleNotFoundError as exc:
    if exc.name != "crash_report":
        raise
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common" / "scripts"))
    from crash_report import redact


def redact_session_text(text: str, depth: int = 0) -> str:
    """Redact structured records and JSON embedded in tool-output strings too."""
    if depth > 12:
        return "(nested content omitted)"
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return redact(text)
    except RecursionError:
        return "(nested content omitted)"

    def clean(value, level):
        if level > 12:
            return "(nested content omitted)"
        if isinstance(value, dict):
            return {
                key: (
                    "<redacted>" if redact(f"{key}=seat-redaction-probe") != f"{key}=seat-redaction-probe"
                    else clean(item, level + 1)
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [clean(item, level + 1) for item in value]
        if isinstance(value, str):
            return redact_session_text(value, level + 1)
        return value

    if isinstance(value, (dict, list)):
        return redact(json.dumps(clean(value, depth + 1), ensure_ascii=False))
    return redact(text)


class SeatSessionLog:
    def __init__(self, path: Path, *, max_bytes: int = 1024 * 1024, backups: int = 2):
        self.path = Path(path)
        self.max_bytes = max(1024, int(max_bytes))
        self.backups = max(1, int(backups))
        self._lock = threading.RLock()
        self._tail = deque(maxlen=32)
        self._sources: dict = {}

    def write(self, source: str, text: str) -> None:
        # Redact BEFORE truncation: cutting off a key or token prefix can hide it.
        safe = redact_session_text(str(text))
        source = redact(str(source)).replace("\n", " ")[:160]
        with self._lock:
            for line in safe.splitlines():
                line = line[:8192]
                self._tail.append(f"{source}: {line}")
                record = (time.strftime("%Y-%m-%dT%H:%M:%S") + f" {source}: {line}\n").encode("utf-8", "replace")
                record = record[:self.max_bytes - 1] + b"\n" if len(record) > self.max_bytes else record
                try:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    size = self.path.stat().st_size if self.path.exists() else 0
                    if size + len(record) > self.max_bytes:
                        for n in range(self.backups, 0, -1):
                            src = self.path if n == 1 else Path(f"{self.path}.{n - 1}")
                            if src.exists():
                                src.replace(Path(f"{self.path}.{n}"))
                    with self.path.open("ab") as stream:
                        stream.write(record)
                except OSError:
                    pass

    def tail(self) -> str:
        with self._lock:
            return "\n".join(self._tail)

    def reset_sources(self) -> None:
        with self._lock:
            self._sources.clear()
            self._tail.clear()

    def collect(self, paths, *, final: bool = False) -> None:
        """Tail complete lines only; never persist partial secret-bearing records."""
        with self._lock:
            for path in paths:
                path = Path(path)
                try:
                    stat = path.stat()
                    identity = (stat.st_dev, stat.st_ino)
                    offset, pending, dropping, old_id = self._sources.get(path, (0, b"", False, identity))
                    if stat.st_size < offset or identity != old_id:
                        offset, pending, dropping = 0, b"", False
                    with path.open("rb") as stream:
                        if final and stat.st_size - offset > 262144:
                            offset, pending, dropping = stat.st_size - 262144, b"", True
                            self.write(path.name, "(skipped backlog; final output follows)")
                        stream.seek(offset)
                        chunk = stream.read(262144)
                        offset = stream.tell()
                    parts = (pending + chunk).split(b"\n")
                    pending = parts.pop()
                    for part in parts:
                        if not dropping:
                            if len(part) <= 65536:
                                self.write(path.name, part.decode("utf-8", "replace"))
                            else:
                                self.write(path.name, "(oversized record omitted)")
                        dropping = False
                    if len(pending) > 65536:
                        pending, dropping = b"", True
                    if final and offset >= stat.st_size:
                        if pending and not dropping:
                            self.write(path.name, pending.decode("utf-8", "replace"))
                        pending = b""
                    self._sources[path] = (offset, pending, dropping, identity)
                except OSError:
                    continue


def console_startup_state() -> dict:
    """Best-effort console metadata only; never capture the environment wholesale."""
    state = {
        "TERM": os.environ.get("TERM", ""),
        "host_process": None, "window_size": None, "buffer_size": None,
        "input_code_page": None, "output_code_page": None,
        "stdin_mode": None, "stdout_mode": None, "stderr_mode": None,
        "vt_input": None, "vt_output": None, "vt_stderr": None,
    }
    if os.name != "nt":
        try:
            size = os.get_terminal_size()
            state["window_size"] = [size.columns, size.lines]
        except OSError:
            pass
        return state
    try:
        from ctypes import wintypes as W

        class Coord(ctypes.Structure):
            _fields_ = [("x", W.SHORT), ("y", W.SHORT)]

        class Rect(ctypes.Structure):
            _fields_ = [(key, W.SHORT) for key in ("left", "top", "right", "bottom")]

        class Info(ctypes.Structure):
            _fields_ = [("size", Coord), ("cursor", Coord), ("attributes", W.WORD),
                        ("window", Rect), ("maximum", Coord)]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        k32.GetStdHandle.restype = W.HANDLE
        k32.GetConsoleWindow.restype = W.HWND
        k32.OpenProcess.restype = W.HANDLE
        k32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
        k32.CloseHandle.argtypes = [W.HANDLE]
        k32.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)]
        user32.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]
        k32.GetConsoleMode.argtypes = [W.HANDLE, ctypes.POINTER(W.DWORD)]
        k32.GetConsoleScreenBufferInfo.argtypes = [W.HANDLE, ctypes.POINTER(Info)]
        for handle_id, name, vt_name, flag in (
            (-10, "stdin_mode", "vt_input", 0x200),
            (-11, "stdout_mode", "vt_output", 0x4),
            (-12, "stderr_mode", "vt_stderr", 0x4),
        ):
            handle = k32.GetStdHandle(handle_id)
            mode = W.DWORD()
            if k32.GetConsoleMode(handle, ctypes.byref(mode)):
                state[name] = mode.value
                state[vt_name] = bool(mode.value & flag)
            if handle_id == -11:
                info = Info()
                if k32.GetConsoleScreenBufferInfo(handle, ctypes.byref(info)):
                    state["buffer_size"] = [info.size.x, info.size.y]
                    state["window_size"] = [info.window.right - info.window.left + 1,
                                            info.window.bottom - info.window.top + 1]
        state["input_code_page"] = k32.GetConsoleCP()
        state["output_code_page"] = k32.GetConsoleOutputCP()
        pid = W.DWORD()
        user32.GetWindowThreadProcessId(k32.GetConsoleWindow(), ctypes.byref(pid))
        state["host_process"] = {"pid": pid.value, "image": None}
        handle = k32.OpenProcess(0x1000, False, pid.value)
        if handle:
            try:
                image, length = ctypes.create_unicode_buffer(32768), W.DWORD(32768)
                if k32.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(length)):
                    state["host_process"]["image"] = image.value
            finally:
                k32.CloseHandle(handle)
    except (OSError, AttributeError):
        pass
    return state
