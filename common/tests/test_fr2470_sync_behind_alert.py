"""FR #2470: Sync-BobiverseWorkTree ALERTs when HEAD stays behind origin/main; docs cover harvest tip hotpatch."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from repo_layout import REPO

COMMON = REPO / "common" / "scripts" / "Bobiverse-Common.ps1"
SYNC = REPO / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"
README = REPO / "README.md"

# FR #7026: README/docs tests are text-only; runtime + Common/Sync source need Windows+git.
_WIN_GIT = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("git"),
    reason="windows + git",
)

HARVEST_HEADING = "### Catch-up / harvest hotpatch when the install lags tip (FR #2470)"


def _fn_body(text: str, name: str) -> str:
    m = re.search(r"function\s+" + re.escape(name) + r"\b", text)
    assert m, name
    rest = text[m.start() :]
    m2 = re.search(r"\nfunction\s+\w+", rest[1:])
    return rest if not m2 else rest[: m2.start() + 1]


def _heading_level(line: str) -> int | None:
    s = line.lstrip()
    if not s.startswith("#"):
        return None
    n = 0
    for ch in s:
        if ch == "#":
            n += 1
        else:
            break
    if n and (len(s) == n or s[n].isspace()):
        return n
    return None


def harvest_section_from_readme(text: str, heading: str = HARVEST_HEADING) -> str:
    """Return markdown from the harvest heading through the next same-or-higher heading.

    FR #7026: do not slice from the first 'hotpatch' (README FR #6989 'hotpatches').
    Fail if the heading is missing; never fall back to a whole-file window.
    """
    idx = text.find(heading)
    assert idx >= 0, "missing harvest heading: %r" % heading
    line_start = text.rfind("\n", 0, idx)
    start = 0 if line_start < 0 else line_start + 1
    first = text[start : text.find("\n", start)]
    level = _heading_level(first)
    assert level is not None, heading
    rest = text[start:]
    lines = rest.splitlines(keepends=True)
    out = [lines[0]]
    in_fence = False
    for line in lines[1:]:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        if not in_fence:
            lv = _heading_level(line.rstrip("\r\n"))
            if lv is not None and lv <= level:
                break
        out.append(line)
    return "".join(out)


_PS_FENCE = re.compile(r"```powershell[^\n]*\r?\n(.*?)```", re.DOTALL | re.IGNORECASE)


def executable_ps_lines(section: str) -> list[str]:
    """Non-comment, non-blank lines inside powershell fences in *section*."""
    lines: list[str] = []
    for m in _PS_FENCE.finditer(section):
        for raw in m.group(1).splitlines():
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            lines.append(s)
    return lines


def harvest_recipe_ok(section: str) -> tuple[bool, str]:
    """FR #7026: fetch, then Sync-BobiverseHarvestScriptsFromOrigin, then -ComposeOnly.

    FR #4783 (Bobiverse-Common.ps1 Sync-BobiverseHarvestScriptsFromOrigin): the
    byte-preserving helper supersedes FR #2470 WriteAllText / UTF8Encoding writer
    tokens. Reject those writers and the WinPS BOM Set-Content pipeline.
    """
    if HARVEST_HEADING not in section and "Catch-up / harvest hotpatch" not in section:
        return False, "missing harvest heading"
    fences = [m.group(1) for m in _PS_FENCE.finditer(section)]
    helper_blocks = [b for b in fences if "Sync-BobiverseHarvestScriptsFromOrigin" in b]
    src = helper_blocks[-1] if helper_blocks else section
    cmds = executable_ps_lines("```powershell\n" + src + "```") if helper_blocks else executable_ps_lines(section)
    blob = "\n".join(cmds)
    if "Set-Content -LiteralPath" in blob:
        return False, "Set-Content -LiteralPath"
    if re.search(r"\|\s*Set-Content", blob):
        return False, "piped Set-Content"
    if "WriteAllText" in blob or "UTF8Encoding" in blob:
        return False, "WriteAllText/UTF8Encoding"
    joined = "\n".join(cmds)
    fetch_i = next((i for i, c in enumerate(cmds) if re.search(r"\bgit\b.*\bfetch\b", c)), None)
    sync_i = next(
        (i for i, c in enumerate(cmds) if "Sync-BobiverseHarvestScriptsFromOrigin" in c),
        None,
    )
    compose_i = next((i for i, c in enumerate(cmds) if "-ComposeOnly" in c), None)
    if fetch_i is None:
        return False, "missing git fetch"
    if sync_i is None:
        return False, "missing Sync-BobiverseHarvestScriptsFromOrigin"
    if compose_i is None:
        return False, "missing -ComposeOnly"
    if not (fetch_i < sync_i < compose_i):
        return False, "order fetch -> helper -> ComposeOnly"
    return True, joined


@_WIN_GIT
def test_fr2470_sync_worktree_counts_behind_and_alerts():
    text = COMMON.read_text(encoding="utf-8")
    body = _fn_body(text, "Sync-BobiverseWorkTree")
    helper = _fn_body(text, "Get-BobiverseWorkTreeBehindCount")
    assert "Get-BobiverseWorkTreeBehindCount" in body
    assert "sync-behind" in body
    assert "FR #2470" in body or "FR#2470" in body or "#2470" in body
    assert "rev-list" in helper
    assert "--count" in helper


@_WIN_GIT
def test_fr2470_from_repo_surfaces_behind_stale():
    t = SYNC.read_text(encoding="utf-8")
    assert "ALERT" in t
    assert "behind" in t.lower()


def test_fr2470_readme_documents_harvest_tip_hotpatch():
    t = README.read_text(encoding="utf-8")
    assert "Invoke-BobiverseHarvest" in t or "harvest" in t.lower()
    assert "ComposeOnly" in t or "hotpatch" in t.lower()
    assert "sync-behind" in t or "behind origin" in t.lower()
    section = harvest_section_from_readme(t)
    ok, why = harvest_recipe_ok(section)
    assert ok, why


@pytest.mark.parametrize(
    "md,expect_ok",
    [
        (
            HARVEST_HEADING
            + "\n\n```powershell\n"
            + "git -C <install> fetch origin\n"
            + ". <install>\\common\\scripts\\Bobiverse-Common.ps1\n"
            + "Sync-BobiverseHarvestScriptsFromOrigin -InstallRoot <install> -Branch main\n"
            + "& <install>\\scripts\\Sync-BobiverseFromRepo.ps1 -Product bob -InstallRoot <install> -ComposeOnly\n"
            + "```\n\n## Pack\n",
            True,
        ),
        (
            HARVEST_HEADING
            + "\n\nSee Sync-BobiverseHarvestScriptsFromOrigin in prose.\n"
            + "```powershell\n# Sync-BobiverseHarvestScriptsFromOrigin -InstallRoot x\n"
            + "git -C x fetch origin\n"
            + "& x\\scripts\\Sync-BobiverseFromRepo.ps1 -ComposeOnly\n```\n",
            False,
        ),
        (
            HARVEST_HEADING
            + "\n\n```powershell\n"
            + "git -C x fetch origin\n"
            + "git show origin/main:common/scripts/Invoke-BobiverseHarvest.ps1 | Set-Content -Encoding utf8 dest.ps1\n"
            + "Sync-BobiverseHarvestScriptsFromOrigin -InstallRoot x\n"
            + "& x\\s.ps1 -ComposeOnly\n```\n",
            False,
        ),
        (
            "## Earlier\n* RecycleSeat hotpatches\n\n## Pack\n",
            False,
        ),
    ],
)
def test_fr7026_harvest_section_helpers_synthetic(md: str, expect_ok: bool):
    if HARVEST_HEADING not in md:
        with pytest.raises(AssertionError):
            harvest_section_from_readme(md)
        assert expect_ok is False
        return
    section = harvest_section_from_readme(md)
    ok, _why = harvest_recipe_ok(section)
    assert ok is expect_ok


@_WIN_GIT
def test_fr2470_ff_blocked_alerts_with_behind_count():
    tmp = Path(os.environ.get("TEMP", ".")) / ("fr2470-%s-%s" % (os.getpid(), int(time.time())))
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    seed = tmp / "seed"
    seed.mkdir()
    ident = ["-c", "user.name=t", "-c", "user.email=t@t"]

    def git(cwd, *a, check=True):
        r = subprocess.run(
            ["git", *ident, "-c", "core.autocrlf=false", "-C", str(cwd), *a],
            capture_output=True,
            text=True,
        )
        if check:
            assert r.returncode == 0, (a, r.stdout, r.stderr)
        return r

    def write(p, text):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")

    git(seed, "init", "-q", "-b", "main")
    write(seed / "common/VERSION", "1.0.0\n")
    write(seed / "common/scripts/c1.ps1", "# c\n")
    write(seed / "common/scripts/Invoke-BobiverseHarvest.ps1", "# harvest v1\n")
    write(seed / "bob/scripts/b1.ps1", "# b\n")
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "i")
    bare = tmp / "remote.git"
    subprocess.run(
        ["git", "clone", "-q", "--bare", str(seed), str(bare)],
        check=True,
        capture_output=True,
    )
    git(seed, "remote", "add", "origin", str(bare))
    ai = tmp / "ai"
    ai.mkdir()
    r = ai / "bob"
    r.mkdir()
    write(r / "VERSION", "0.0.1\n")
    write(r / "scripts/old.ps1", "# old\n")

    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in (
            "BOBIVERSE_REPO",
            "BOBIVERSE_NO_UPDATE",
            "BOBIVERSE_KEEP_BRANCH",
            "BOBIVERSE_FETCH_TIMEOUT_SEC",
            "BOBIVERSE_FETCH_RETRIES",
            "BOB_AI_ROOT",
            "BOBIVERSE_REMOTE",
        )
    }
    env["BOB_AI_ROOT"] = str(ai)
    env["BOBIVERSE_REMOTE"] = str(bare)

    def sync():
        return subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SYNC),
                "-Product",
                "bob",
                "-InstallRoot",
                str(r),
            ],
            capture_output=True,
            text=True,
            timeout=240,
            env=env,
        )

    out1 = sync()
    assert out1.returncode == 0, out1.stdout + out1.stderr
    # Block ff with a local edit, then push tip ahead so behind count is > 0.
    write(r / "bob/scripts/b1.ps1", "# LOCAL\n")
    write(seed / "bob/scripts/b1.ps1", "# UP\n")
    write(seed / "common/scripts/Invoke-BobiverseHarvest.ps1", "# harvest v2 tip\n")
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "up")
    git(seed, "push", "-q", "origin", "main")
    out2 = sync()
    text = out2.stdout + out2.stderr
    assert out2.returncode == 0, text
    # FR #7053 / #7024: dirty bob/scripts/b1.ps1 is not a park-allowlist hotpatch.
    # Parking it (FR #6989-all-dirty) made ff succeed and dropped the ALERT.
    assert (r / "bob/scripts/b1.ps1").read_text(encoding="utf-8") == "# LOCAL\n"
    assert "skip-not-hotpatch" in text, text
    assert "ALERT" in text, text
    assert "ff-only not possible" in text or "sync-ff-failed" in text, text
    assert re.search(r"behind origin/\w+ by \d+", text, re.I), text
    shutil.rmtree(tmp, ignore_errors=True)
