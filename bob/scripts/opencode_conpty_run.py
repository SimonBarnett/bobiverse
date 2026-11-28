"""Run a command on a Windows pseudoconsole and append output as it arrives.

OpenCode block-buffers when stdout is a file. A ConPTY makes stdout a console,
so each chunk is written to the capture file before the process exits.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
from pathlib import Path


def _run_conpty(argv: list[str], cwd: str, out_path: Path) -> int:
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class COORD(ctypes.Structure):
        _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

    class STARTUPINFO(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR),
            ("lpTitle", wintypes.LPWSTR),
            ("dwX", wintypes.DWORD),
            ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD),
            ("dwYSize", wintypes.DWORD),
            ("dwXCountChars", wintypes.DWORD),
            ("dwYCountChars", wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD),
            ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
            ("hStdInput", wintypes.HANDLE),
            ("hStdOutput", wintypes.HANDLE),
            ("hStdError", wintypes.HANDLE),
        ]

    class STARTUPINFOEX(ctypes.Structure):
        _fields_ = [("StartupInfo", STARTUPINFO), ("lpAttributeList", ctypes.c_void_p)]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", wintypes.HANDLE),
            ("hThread", wintypes.HANDLE),
            ("dwProcessId", wintypes.DWORD),
            ("dwThreadId", wintypes.DWORD),
        ]

    if ctypes.sizeof(STARTUPINFO) != 104 or ctypes.sizeof(STARTUPINFOEX) != 112:
        raise OSError(
            f"STARTUPINFOEX layout {ctypes.sizeof(STARTUPINFO)}/"
            f"{ctypes.sizeof(STARTUPINFOEX)} is not the x64 Windows layout"
        )

    HPCON = wintypes.HANDLE
    k32.CreatePipe.argtypes = [
        ctypes.POINTER(wintypes.HANDLE),
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    k32.CreatePipe.restype = wintypes.BOOL
    k32.CreatePseudoConsole.argtypes = [
        COORD,
        wintypes.HANDLE,
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(HPCON),
    ]
    k32.CreatePseudoConsole.restype = ctypes.c_long
    k32.ClosePseudoConsole.argtypes = [HPCON]
    k32.ClosePseudoConsole.restype = None
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.restype = wintypes.BOOL
    k32.ReadFile.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    ]
    k32.ReadFile.restype = wintypes.BOOL
    k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k32.WaitForSingleObject.restype = wintypes.DWORD
    k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k32.GetExitCodeProcess.restype = wintypes.BOOL
    k32.HeapAlloc.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_size_t]
    k32.HeapAlloc.restype = ctypes.c_void_p
    k32.GetProcessHeap.argtypes = []
    k32.GetProcessHeap.restype = wintypes.HANDLE
    k32.InitializeProcThreadAttributeList.argtypes = [
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    k32.InitializeProcThreadAttributeList.restype = wintypes.BOOL
    k32.UpdateProcThreadAttribute.argtypes = [
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.c_size_t,
        wintypes.LPVOID,
        ctypes.c_size_t,
        wintypes.LPVOID,
        wintypes.LPVOID,
    ]
    k32.UpdateProcThreadAttribute.restype = wintypes.BOOL
    k32.CreateProcessW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.BOOL,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.LPCWSTR,
        ctypes.POINTER(STARTUPINFOEX),
        ctypes.POINTER(PROCESS_INFORMATION),
    ]
    k32.CreateProcessW.restype = wintypes.BOOL

    extended = 0x00080000
    pseudo_attr = 0x00020016
    infinite = 0xFFFFFFFF

    in_r, in_w = wintypes.HANDLE(), wintypes.HANDLE()
    out_r, out_w = wintypes.HANDLE(), wintypes.HANDLE()
    if not k32.CreatePipe(ctypes.byref(in_r), ctypes.byref(in_w), None, 0):
        raise OSError("CreatePipe input")
    if not k32.CreatePipe(ctypes.byref(out_r), ctypes.byref(out_w), None, 0):
        raise OSError("CreatePipe output")
    hpc = HPCON()
    hr = int(k32.CreatePseudoConsole(COORD(120, 40), in_r, out_w, 0, ctypes.byref(hpc)))
    # ConHost duplicates these. Close the PTY ends so EOF can arrive later.
    k32.CloseHandle(in_r)
    k32.CloseHandle(out_w)
    if hr != 0 or not hpc.value:
        k32.CloseHandle(in_w)
        k32.CloseHandle(out_r)
        raise OSError(f"CreatePseudoConsole 0x{hr & 0xFFFFFFFF:08X}")

    size = ctypes.c_size_t(0)
    k32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
    heap = k32.GetProcessHeap()
    mem = k32.HeapAlloc(heap, 0, size.value)
    if not mem:
        raise OSError("HeapAlloc attribute list")
    if not k32.InitializeProcThreadAttributeList(mem, 1, 0, ctypes.byref(size)):
        raise OSError(f"InitializeProcThreadAttributeList winerr={ctypes.get_last_error()}")
    # Sample passes the HPCON value itself (not a pointer to it).
    if not k32.UpdateProcThreadAttribute(
        mem,
        0,
        pseudo_attr,
        hpc,
        ctypes.sizeof(HPCON),
        None,
        None,
    ):
        raise OSError(f"UpdateProcThreadAttribute winerr={ctypes.get_last_error()}")

    si = STARTUPINFOEX()
    si.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEX)
    si.lpAttributeList = mem
    pi = PROCESS_INFORMATION()
    cmdline = subprocess.list2cmdline(argv)
    buf = ctypes.create_unicode_buffer(cmdline)
    ok = k32.CreateProcessW(
        None,
        buf,
        None,
        None,
        False,
        extended,
        None,
        cwd or None,
        ctypes.byref(si),
        ctypes.byref(pi),
    )
    if not ok:
        err = ctypes.get_last_error()
        k32.ClosePseudoConsole(hpc)
        k32.CloseHandle(out_r)
        k32.CloseHandle(in_w)
        raise OSError(f"CreateProcessW winerr={err}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    read_error: list[BaseException] = []

    def _drain() -> None:
        try:
            with out_path.open("ab", buffering=0) as fh:
                while True:
                    n = wintypes.DWORD(0)
                    block = ctypes.create_string_buffer(4096)
                    read_ok = k32.ReadFile(out_r, block, 4096, ctypes.byref(n), None)
                    if n.value:
                        fh.write(block.raw[: n.value])
                        fh.flush()
                    if not read_ok or n.value == 0:
                        break
        except BaseException as exc:  # noqa: BLE001 — surfaced after join
            read_error.append(exc)

    reader = threading.Thread(target=_drain, name="opencode-conpty-drain", daemon=True)
    reader.start()
    # Closing the pseudoconsole unblocks ReadFile. Do that only after the child exits
    # so the capture file already holds the bytes the child wrote.
    k32.WaitForSingleObject(pi.hProcess, infinite)
    code = wintypes.DWORD(0)
    k32.GetExitCodeProcess(pi.hProcess, ctypes.byref(code))
    k32.ClosePseudoConsole(hpc)
    k32.CloseHandle(in_w)
    reader.join(timeout=5)
    k32.CloseHandle(out_r)
    k32.CloseHandle(pi.hThread)
    k32.CloseHandle(pi.hProcess)
    if read_error:
        raise read_error[0]
    return int(code.value)


def _windowless_host_exit() -> int | None:
    """A console-subsystem host steals the child's stdout away from the ConPTY pipe.

    pythonw.exe has no console, so the child's console is the pseudoconsole and
    each write lands in the capture file. Re-enter there and wait.
    """
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        return None
    pyw = exe.with_name("pythonw.exe")
    if not pyw.is_file():
        return None
    proc = subprocess.run([str(pyw), *sys.argv], check=False)
    return int(proc.returncode)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        delegated = _windowless_host_exit()
        if delegated is not None:
            return delegated
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--err", required=True)
    p.add_argument("--cwd", default="")
    p.add_argument("--argv-file", required=True)
    ns = p.parse_args(argv)
    cmd = json.loads(Path(ns.argv_file).read_text(encoding="utf-8"))
    if not isinstance(cmd, list) or not cmd:
        return 2
    Path(ns.err).write_bytes(b"")
    return _run_conpty([str(x) for x in cmd], ns.cwd, Path(ns.out))


if __name__ == "__main__":
    sys.exit(main())
