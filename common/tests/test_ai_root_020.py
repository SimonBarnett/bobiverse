"""t780u: the <drive>:\\ai root is DISCOVERED on the fixed disks, never assumed to be C:\\ai.

Three implementations share one rule set and are tested here with fake "drives" (temp dirs):
  * ai_root.py                       (worker exe, gh_filer)
  * Get-BobiverseAiRoot (Common.ps1) (every installer / updater / Start-* script)
  * FindAiRoot.js                    (MSI immediate custom action; WiX has no PowerShell)
"""
import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from repo_layout import REPO

import ai_root
from ai_root import Disk, select_ai_root

WIN = sys.platform == "win32"
COMMON = REPO / "common" / "scripts" / "Bobiverse-Common.ps1"
FIND_JS = REPO / "common" / "packaging" / "FindAiRoot.js"


def _mk(tmp: Path, letter: str, ai: bool = False, products=()):
    root = tmp / letter
    root.mkdir(parents=True, exist_ok=True)
    if ai:
        (root / "ai").mkdir()
        for p in products:
            (root / "ai" / p).mkdir()
    return str(root) + "\\"


# ------------------------------------------------------------------ python twin
def test_py_ai_on_d_only(tmp_path):
    disks = [Disk(_mk(tmp_path, "C"), 3), Disk(_mk(tmp_path, "D", ai=True), 3)]
    sel = select_ai_root(disks, [], "C:")
    assert sel.found and sel.path == str(tmp_path / "D" / "ai")


def test_py_ai_on_c_and_d_prefers_installs_then_services_then_system(tmp_path):
    c = _mk(tmp_path, "C", ai=True)
    d = _mk(tmp_path, "D", ai=True, products=("bob", "airc"))
    sel = select_ai_root([Disk(c, 3), Disk(d, 3)], [], "C:")
    assert sel.path == str(tmp_path / "D" / "ai") and "install" in sel.reason
    # equal installs -> services decide
    c = _mk(tmp_path, "C2", ai=True)
    d = _mk(tmp_path, "D2", ai=True)
    svc = [str(tmp_path / "D2" / "ai" / "jeeves" / "scripts")]
    sel = select_ai_root([Disk(c, 3), Disk(d, 3)], svc, "C:")
    assert sel.path == str(tmp_path / "D2" / "ai") and "service" in sel.reason


def test_py_none_default_is_system_drive_and_not_created(tmp_path):
    disks = [Disk(_mk(tmp_path, "C"), 3), Disk(_mk(tmp_path, "D"), 3)]
    sel = select_ai_root(disks, [], "C:")
    assert not sel.found and sel.path == "C:\\ai"
    assert not (tmp_path / "C" / "ai").exists() and not (tmp_path / "D" / "ai").exists()


@pytest.mark.parametrize("dtype", [2, 4, 5, 1, 6])
def test_py_removable_network_cd_ignored(tmp_path, dtype):
    disks = [Disk(_mk(tmp_path, "C"), 3), Disk(_mk(tmp_path, "E", ai=True, products=("bob", "jeeves")), dtype)]
    sel = select_ai_root(disks, [], "C:")
    assert not sel.found and sel.path == "C:\\ai"
    # ... and a fixed disk wins even when the ignored one has more installs
    disks.append(Disk(_mk(tmp_path, "D", ai=True), 3))
    assert select_ai_root(disks, [], "C:").path == str(tmp_path / "D" / "ai")


def test_py_override_wins(tmp_path):
    disks = [Disk(_mk(tmp_path, "D", ai=True), 3)]
    assert select_ai_root(disks, [], "C:", override="X:\\myai\\").path == "X:\\myai"
    assert ai_root.find_ai_root(env={"BOB_AI_ROOT": "X:\\myai"}) == "X:\\myai"
    assert ai_root.product_root("bob", env={"BOB_AI_ROOT": "X:\\myai"}) == "X:\\myai\\bob"


def test_py_find_does_not_create_when_found(tmp_path):
    d = _mk(tmp_path, "D", ai=True)
    before = sorted(p.name for p in (tmp_path / "D").iterdir())
    got = ai_root.find_ai_root(create=True, disks=[Disk(d, 3)], services=[], system_drive="C:", env={})
    assert got == str(tmp_path / "D" / "ai")
    assert sorted(p.name for p in (tmp_path / "D").iterdir()) == before
    assert list((tmp_path / "D" / "ai").iterdir()) == []


def test_py_create_only_when_none(tmp_path):
    root = tmp_path / "SYS"
    root.mkdir()
    # fake system drive = tmp dir: select_ai_root joins "<sys>\\ai"
    got = ai_root.find_ai_root(create=True, disks=[], services=[], system_drive=str(root), env={})
    assert Path(got) == root / "ai" and (root / "ai").is_dir()


def test_py_fixed_disks_only_fixed():
    if not WIN:
        pytest.skip("windows only")
    ds = ai_root.fixed_disks()
    assert ds and all(d.drive_type == 3 for d in ds)


# ------------------------------------------------------------------ PowerShell (Common.ps1)
def _ps(tmp_path, body: str) -> dict:
    script = tmp_path / "t.ps1"
    script.write_text(
        "$ErrorActionPreference='Stop'\n. '%s'\n$o = & {\n%s\n}\n$o | ConvertTo-Json -Compress -Depth 5\n" % (COMMON, textwrap.dedent(body)),
        encoding="utf-8-sig",
    )
    env = {k: v for k, v in os.environ.items() if k != "BOB_AI_ROOT"}
    r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                       capture_output=True, text=True, timeout=120, env=env)
    assert r.returncode == 0, r.stderr + r.stdout
    return json.loads(r.stdout.strip().splitlines()[-1])


def _disks(*pairs):
    return "@(" + ",".join("[pscustomobject]@{Root='%s';DriveType=%d}" % (r, t) for r, t in pairs) + ")"


@pytest.mark.skipif(not WIN, reason="PowerShell harness")
def test_ps_ai_on_d_only(tmp_path):
    c, d = _mk(tmp_path, "C"), _mk(tmp_path, "D", ai=True)
    o = _ps(tmp_path, f"Select-BobiverseAiRoot -Disks {_disks((c, 3), (d, 3))} -SystemDrive 'C:'")
    assert o["Found"] is True and Path(o["Path"]) == tmp_path / "D" / "ai"


@pytest.mark.skipif(not WIN, reason="PowerShell harness")
def test_ps_c_and_d_prefers_installs_then_services(tmp_path):
    c, d = _mk(tmp_path, "C", ai=True), _mk(tmp_path, "D", ai=True, products=("bob", "ergo"))
    o = _ps(tmp_path, f"Select-BobiverseAiRoot -Disks {_disks((c, 3), (d, 3))} -SystemDrive 'C:'")
    assert Path(o["Path"]) == tmp_path / "D" / "ai" and "install" in o["Reason"]
    c, d = _mk(tmp_path, "C2", ai=True), _mk(tmp_path, "D2", ai=True)
    svc = str(tmp_path / "D2" / "ai" / "airc")
    o = _ps(tmp_path, f"Select-BobiverseAiRoot -Disks {_disks((c, 3), (d, 3))} -ServiceDirs @('{svc}') -SystemDrive 'C:'")
    assert Path(o["Path"]) == tmp_path / "D2" / "ai" and "service" in o["Reason"]


@pytest.mark.skipif(not WIN, reason="PowerShell harness")
def test_ps_none_default_and_not_created(tmp_path):
    c, d = _mk(tmp_path, "C"), _mk(tmp_path, "D")
    o = _ps(tmp_path, f"Select-BobiverseAiRoot -Disks {_disks((c, 3), (d, 3))} -SystemDrive 'Q:'")
    assert o["Found"] is False and o["Path"] == "Q:\\ai"
    # Get-BobiverseAiRoot WITHOUT -Create never makes anything
    o = _ps(tmp_path, f"[pscustomobject]@{{p=(Get-BobiverseAiRoot -Disks {_disks((c, 3))} -ServiceDirs @() -SystemDrive 'Q:' -Override '')}}")
    assert o["p"] == "Q:\\ai"
    assert not (tmp_path / "C" / "ai").exists() and not (tmp_path / "D" / "ai").exists()


@pytest.mark.skipif(not WIN, reason="PowerShell harness")
@pytest.mark.parametrize("dtype", [2, 4, 5])
def test_ps_removable_network_cd_ignored(tmp_path, dtype):
    c, e = _mk(tmp_path, "C"), _mk(tmp_path, "E", ai=True, products=("bob", "jeeves", "airc"))
    o = _ps(tmp_path, f"Select-BobiverseAiRoot -Disks {_disks((c, 3), (e, dtype))} -SystemDrive 'Q:'")
    assert o["Found"] is False and o["Path"] == "Q:\\ai"


@pytest.mark.skipif(not WIN, reason="PowerShell harness")
def test_ps_no_creation_when_found_and_creation_when_none(tmp_path):
    d = _mk(tmp_path, "D", ai=True)
    before = sorted(p.name for p in (tmp_path / "D").iterdir())
    o = _ps(tmp_path, f"[pscustomobject]@{{p=(Get-BobiverseAiRoot -Create -Disks {_disks((d, 3))} -ServiceDirs @() -SystemDrive 'C:' -Override '')}}")
    assert Path(o["p"]) == tmp_path / "D" / "ai"
    assert sorted(p.name for p in (tmp_path / "D").iterdir()) == before and list((tmp_path / "D" / "ai").iterdir()) == []
    # none found: -Create makes <SystemDrive>\ai. Use a throw-away subst drive as the "system drive".
    used = subprocess.run(["cmd", "/c", "subst"], capture_output=True, text=True).stdout

    def _drive_free(letter: str) -> bool:
        # FR #3396: Path.exists() can raise OSError (WinError 1326) on stale mapped letters.
        try:
            return not Path(f"{letter}:\\").exists()
        except OSError:
            return False

    free = [chr(c) for c in range(ord("T"), ord("Z") + 1) if _drive_free(chr(c))]
    if not free:
        pytest.skip("no free drive letter for subst")
    L = free[0]
    sysroot = tmp_path / "SYS"
    sysroot.mkdir()
    subprocess.run(["subst", f"{L}:", str(sysroot)], check=True)
    try:
        o = _ps(tmp_path, f"[pscustomobject]@{{p=(Get-BobiverseAiRoot -Create -Disks @() -ServiceDirs @() -SystemDrive '{L}:' -Override '')}}")
        assert o["p"] == f"{L}:\\ai" and (sysroot / "ai").is_dir()
        # ProductRoot / second call: now found? (Disks injected empty) -> still same path, idempotent
        o = _ps(tmp_path, f"[pscustomobject]@{{p=(Get-BobiverseAiRoot -Create -Disks @() -ServiceDirs @() -SystemDrive '{L}:' -Override '')}}")
        assert o["p"] == f"{L}:\\ai"
    finally:
        subprocess.run(["subst", f"{L}:", "/d"], check=False)


@pytest.mark.skipif(not WIN, reason="PowerShell harness")
def test_ps_override_env_and_live_fixed_disks(tmp_path):
    script = tmp_path / "o.ps1"
    script.write_text(". '%s'\n$env:BOB_AI_ROOT='X:\\override\\'\n$a = Get-BobiverseAiRoot\n$b = Get-BobiverseProductRoot -Product bob\n"
                      "$env:BOB_AI_ROOT=''\n$d = @(Get-BobiverseFixedDisks)\n"
                      "[pscustomobject]@{a=$a;b=$b;n=$d.Count;t=@($d | %% { $_.DriveType } | Select-Object -Unique)} | ConvertTo-Json -Compress\n" % COMMON,
                      encoding="utf-8-sig")
    r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    o = json.loads(r.stdout.strip().splitlines()[-1])
    assert o["a"] == "X:\\override" and o["b"] == "X:\\override\\bob"
    assert o["n"] >= 1 and o["t"] in (3, [3])


# ------------------------------------------------------------------ MSI custom action (JScript)
def _js(tmp_path, body: str, env_extra=None) -> str:
    wrapper = tmp_path / "w.js"
    wrapper.write_text(
        "var fso = new ActiveXObject('Scripting.FileSystemObject');\n"
        "eval(fso.OpenTextFile('%s', 1).ReadAll());\n%s\n" % (str(FIND_JS).replace("\\", "\\\\"), body),
        encoding="ascii",
    )
    env = {k: v for k, v in os.environ.items() if k != "BOB_AI_ROOT"}
    env.update(env_extra or {})
    r = subprocess.run(["cscript.exe", "//nologo", str(wrapper)], capture_output=True, text=True, timeout=60, env=env)
    assert r.returncode == 0, r.stderr + r.stdout
    return r.stdout.strip()


def _pick(tmp_path, drives, sysd="C:", svc="[]", override=""):
    js = ",".join("{letter:'%s',type:%d,hasAi:%s,installs:%d}" % (l, t, str(a).lower(), n) for l, t, a, n in drives)
    return _js(tmp_path, "WScript.Echo(bobPickAiRoot({override:%s,systemDrive:'%s',drives:[%s],svcLetters:%s}));" % (json.dumps(override), sysd, js, svc))


@pytest.mark.skipif(not WIN, reason="cscript harness")
def test_js_rules(tmp_path):
    assert _pick(tmp_path, [("C", 2, False, 0), ("D", 2, True, 0)]) == "D:\\ai"                      # ai on D only
    assert _pick(tmp_path, [("C", 2, True, 0), ("D", 2, True, 2)]) == "D:\\ai"                       # C and D: installs win
    assert _pick(tmp_path, [("C", 2, True, 1), ("D", 2, True, 1)], svc="['D']") == "D:\\ai"          # then services
    assert _pick(tmp_path, [("C", 2, True, 0), ("D", 2, True, 0)]) == "C:\\ai"                       # then system drive
    assert _pick(tmp_path, [("C", 2, False, 0), ("D", 2, False, 0)]) == "C:\\ai"                     # none -> system drive
    assert _pick(tmp_path, [("C", 2, False, 0), ("D", 2, False, 0)], sysd="E:") == "E:\\ai"
    for t in (1, 3, 4, 5, 6):                                                                         # removable(1)/remote(3)/cd(4)/ram(6)... only 2 = fixed
        assert _pick(tmp_path, [("C", 2, False, 0), ("F", t, True, 3)]) == "C:\\ai"
    assert _pick(tmp_path, [("D", 2, True, 0)], override="X:\\mine\\") == "X:\\mine"


@pytest.mark.skipif(not WIN, reason="cscript harness")
def test_js_live_override_and_fixed_scan(tmp_path):
    assert _js(tmp_path, "WScript.Echo(bobFindAiRoot());", {"BOB_AI_ROOT": "Z:\\mine"}) == "Z:\\mine"
    live = _js(tmp_path, "WScript.Echo(bobFindAiRoot());")
    assert re.fullmatch(r"[A-Za-z]:\\ai", live), live
    drive = live[:2]
    # the answer is either an existing \ai on a FIXED disk or the system drive default
    assert Path(live).is_dir() or drive.upper() == os.environ.get("SystemDrive", "C:").upper()


def test_js_has_no_hardcoded_c_ai_and_never_creates_folders():
    t = FIND_JS.read_text(encoding="utf-8-sig")
    assert not re.search(r"C:\\\\ai", t, re.I)
    assert "CreateFolder" not in t and "mkdir" not in t.lower()


# ------------------------------------------------------------------ nothing hard-codes C:\ai any more
ALLOWED = {
    # discovery implementations + their documentation of the default / fallbacks
    "common/scripts/ai_root.py", "common/scripts/Bobiverse-Common.ps1",
    # last-resort fallbacks when Common is not shipped next to the script
    "common/scripts/Update-BobiverseService.ps1", "bob/scripts/bob_worker.py",
    # other tools' trees (agentic_*), vendored tray (pinned upstream; patched only where it names the bobiverse install)
    "common/scripts/bob_recycle.py", "common/scripts/bobstat.py", "common/scripts/protect.py",
    "bob/scripts/Sync-BobTrayFromAgenticBuild.ps1",
    # last-resort fallbacks when RepoRoot/AiRoot not passed (disk reclaim helpers)
    "common/scripts/Clear-BobiverseJobWorktrees.ps1",
    "common/scripts/Clear-BobiverseSeatDisk.ps1",
}
DEFAULT_RE = re.compile(r"""(\$\w*(Root|Dir)\w*\s*=\s*['"]C:\\ai|\[string\]\$\w+\s*=\s*['"]C:\\ai|SetDirectory[^>]*C:\\ai|Join-Path\s+['"]C:\\ai)""", re.I)


def test_installers_updater_wix_tray_have_no_hardcoded_default():
    bad = []
    for ext in ("*.ps1", "*.py", "*.wxs", "*.cmd"):
        for p in REPO.rglob(ext):
            rel = p.relative_to(REPO).as_posix()
            if "third_party" in rel or "/tests/" in rel or rel in ALLOWED or ".git/" in rel:
                continue
            for i, line in enumerate(p.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1):
                if DEFAULT_RE.search(line):
                    bad.append(f"{rel}:{i}: {line.strip()[:120]}")
    assert not bad, "hard-coded C:\\ai defaults:\n" + "\n".join(bad)


def test_installers_resolve_through_the_root_helper():
    for rel, needle in [
        ("bob/scripts/Install-Bob.ps1", "Get-BobiverseAiRoot -Create"),
        ("jeeves/scripts/Install-Jeeves.ps1", "Get-BobiverseAiRoot -Create"),
        ("airc/scripts/Install-Airc.ps1", "Get-BobiverseAiRoot -Create"),
        ("jeeves/scripts/Install-BobIrcd.ps1", "Get-BobiverseAiRoot -Create"),
        ("common/scripts/Sync-BobiverseFromRepo.ps1", "Get-BobiverseProductRoot"),
        ("common/scripts/Update-BobiverseService.ps1", "Get-BobiverseProductRoot"),
        ("common/scripts/Complete-BobiverseServiceLogon.ps1", "Get-BobiverseProductRoot"),
        ("bob/scripts/Start-BobTray.ps1", "Get-BobiverseProductRoot"),
    ]:
        assert needle in (REPO / rel).read_text(encoding="utf-8-sig"), rel
    for rel in ("bob/scripts/Install-Bob.ps1", "jeeves/scripts/Install-Jeeves.ps1", "airc/scripts/Install-Airc.ps1"):
        assert re.search(r"\[string\]\$InstallRoot = ''", (REPO / rel).read_text(encoding="utf-8-sig")), rel


def test_pack_wix_uses_find_ai_root_not_a_fixed_install_dir():
    t = (REPO / "common/scripts/Pack-BobiverseRelease.ps1").read_text(encoding="utf-8-sig")
    assert 'CustomAction Id="FindAiRoot"' in t and 'JScriptCall="FindAiRoot"' in t
    assert 'Property="INSTALLDIR" Value="[AIROOT]' in t
    assert "<SetDirectory" not in t
    assert '-InstallRoot &quot;[INSTALLDIR].&quot;' in t   # the installer is told the MSI's own choice
    assert 'Before="CostInitialize"' in t and 'Before="CostFinalize"' in t