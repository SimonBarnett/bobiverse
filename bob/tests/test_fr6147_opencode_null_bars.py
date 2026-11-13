"""Compiled OpenCode rows for the MarchHare null snapshot.

The installed card painted ``OpenCode n/a`` and no tracks because
``opencode_window_lines`` was empty. FR #7017: draw the three Go windows only
(never free), and must not turn unknown into a 100% fill.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAINT = ROOT / "tray" / "dialogs" / "OpencodePaint.cs"

DRIVER = r"""
using System;
using System.Collections;
using System.Collections.Generic;

class Driver
{
    static int Fail(int code, string why)
    {
        Console.Error.WriteLine(why);
        return code;
    }

    static int Main()
    {
        var failed = BobDialogs.OpencodePaint.Rows("OpenCode  go n/a", new ArrayList(), null);
        if (failed.Count != 3) return Fail(1, "expected 3 Go rows, got " + failed.Count);
        string[] ids = new string[] { "rolling", "week", "month" };
        for (int i = 0; i < 3; i++)
        {
            if (failed[i].Id != ids[i]) return Fail(2, "id " + failed[i].Id);
            if (failed[i].Known) return Fail(3, "unknown row marked known: " + failed[i].Heading);
            if (failed[i].Pct != 0) return Fail(4, "unknown pct " + failed[i].Pct);
            if (failed[i].Heading.IndexOf("100%") >= 0) return Fail(5, failed[i].Heading);
            if (failed[i].Heading.IndexOf("Starts on first use") >= 0) return Fail(6, failed[i].Heading);
            if (failed[i].Heading.IndexOf("free") >= 0) return Fail(7, "free row leaked: " + failed[i].Heading);
        }
        if (failed[0].Heading.IndexOf("rolling") < 0) return Fail(8, failed[0].Heading);
        if (failed[1].Heading.IndexOf("weekly") < 0) return Fail(9, failed[1].Heading);
        if (failed[2].Heading.IndexOf("monthly") < 0) return Fail(10, failed[2].Heading);

        var lines = new ArrayList();
        lines.Add("go rolling  Starts on first use  (0% used)");
        lines.Add("go weekly  72% used · 28% rem  reset 1d 2h");
        lines.Add("go monthly  36% used · 64% rem  reset 26d 18h");
        var fromLines = BobDialogs.OpencodePaint.Rows("OpenCode  go weekly 28%", lines, null);
        if (fromLines.Count != 3) return Fail(11, "lines");
        if (fromLines[0].Known) return Fail(13, "unstarted painted as a quota");
        if (!fromLines[1].Known || fromLines[1].Pct != 28) return Fail(14, "week rem");
        if (!fromLines[2].Known || fromLines[2].Pct != 64) return Fail(15, "month rem");

        var bars = new ArrayList();
        var week = new Hashtable();
        week["id"] = "week";
        week["heading"] = "go weekly  100% used · 0% rem";
        week["known"] = true;
        week["pct"] = 0;
        bars.Add(week);
        var unk = new Hashtable();
        unk["id"] = "rolling";
        unk["heading"] = "go rolling  n/a";
        unk["known"] = false;
        unk["pct"] = 100;
        bars.Add(unk);
        var fromBars = BobDialogs.OpencodePaint.Rows("x", null, bars);
        if (fromBars.Count != 2) return Fail(16, "bars");
        if (!fromBars[0].Known || fromBars[0].Pct != 0) return Fail(17, "exhausted must stay 0");
        if (fromBars[1].Known || fromBars[1].Pct != 0) return Fail(18, "unknown pct 100 was kept");
        Console.WriteLine("ok");
        return 0;
    }
}
"""


def test_compiled_renderer_draws_unknown_pools_for_null_snapshot(tmp_path: Path):
    mcs = shutil.which("mcs")
    if not mcs:
        import pytest

        pytest.skip("mcs not available")
    src = tmp_path / "Driver.cs"
    src.write_text(DRIVER, encoding="utf-8")
    exe = tmp_path / "opencode-paint.exe"
    proc = subprocess.run(
        [mcs, "-sdk:4", "-nologo", "-out:" + str(exe), str(PAINT), str(src)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    run = subprocess.run(
        ["mono", str(exe)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert run.returncode == 0, run.stderr or run.stdout
    assert "ok" in run.stdout
