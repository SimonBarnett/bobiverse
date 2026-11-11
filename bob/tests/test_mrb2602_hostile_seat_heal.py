"""MRB #2602 history + FR #3180: seat-heal removed; manual-only gates.

Locks Watchdog HealEngine-only, no HealWorkerSeats Launch, Ensure report-only,
and docs/skill FR #3180 markers.
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

BOB_TRAY = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
ENSURE = ROOT / "bob" / "scripts" / "Ensure-BobWorkerSeats.ps1"
POST = ROOT / "common" / "docs" / "post-install.md"
SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
WORKER_PY = ROOT / "bob" / "scripts" / "bob_worker.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_mrb2602_watchdog_heals_engine_not_seats():
    t = _read(BOB_TRAY)
    wd = t[t.find("void Watchdog()") :]
    wd = wd[: wd.find("\n        void ", 1)] if "\n        void " in wd[1:] else wd
    assert "HealEngine()" in wd
    assert "HealWorkerSeats()" not in wd
    assert "ObserveWorkerSeats" in wd or "seat-exit" in t


def test_mrb2602_no_heal_worker_seats_launch_path():
    t = _read(BOB_TRAY)
    assert "MaxWorkers = 2" in t
    assert "void HealWorkerSeats" not in t
    assert "seat-exit" in t
    assert "not restarted" in t


def _csharp_method_bodies(src: str, sig_prefix: str) -> list[tuple[str, str]]:
    """Return (signature, body) for each method whose signature starts with sig_prefix.

    Bodies are extracted by brace matching from the opening ``{`` after the signature.
    Do not slice to the next ``public static`` — that misses overloads that forward.
    """
    out: list[tuple[str, str]] = []
    start = 0
    while True:
        i = src.find(sig_prefix, start)
        if i < 0:
            break
        brace = src.find("{", i)
        if brace < 0:
            break
        sig = src[i:brace].strip()
        depth = 0
        j = brace
        while j < len(src):
            c = src[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    out.append((sig, src[brace : j + 1]))
                    start = j + 1
                    break
            j += 1
        else:
            break
    return out


def test_mrb2602_launch_cap_refusal_still_gates():
    """Hostile: every Launch route enforces CapRefusal before any process start.

    FR #6673: the 4-arg overload only forwards; CapRefusal lives on the 6-arg
    (IDictionary childEnv) overload. A first-overload string slice is a false
    release blocker — walk the overload chain instead.
    """
    t = _read(BOB_TRAY)
    overloads = _csharp_method_bodies(t, "public static int Launch(")
    assert len(overloads) >= 2, "expected Launch overloads"

    guarded: list[tuple[str, str]] = []
    forwarding: list[tuple[str, str]] = []
    for sig, body in overloads:
        if "CapRefusal(" in body:
            guarded.append((sig, body))
        else:
            forwarding.append((sig, body))

    assert len(guarded) == 1, "exactly one Launch overload must call CapRefusal"
    g_sig, g_body = guarded[0]
    assert "IDictionary childEnv" in g_sig, "guarded Launch must take IDictionary childEnv"
    assert "CapRefusal(mode)" in g_body

    # Refusal branch assigns error and returns 0 before any describe/start.
    assert "error = refusal" in g_body or "error=refusal" in g_body.replace(" ", "")
    assert "return 0" in g_body
    cap_i = g_body.find("CapRefusal(mode)")
    desc_i = g_body.find("TryDescribeLaunch")
    create_i = g_body.find("CreateProcessW")
    assert cap_i >= 0
    assert desc_i < 0 or cap_i < desc_i
    assert create_i < 0 or cap_i < create_i
    # First return 0 after CapRefusal is the refusal path (before CreateProcessW).
    ret0 = g_body.find("return 0", cap_i)
    assert ret0 >= 0 and (create_i < 0 or ret0 < create_i)

    for sig, body in forwarding:
        assert "Launch(" in body, f"unguarded overload must forward: {sig}"
        assert "mode" in body  # mode must pass through
        assert "CreateProcessW" not in body
        assert "TryDescribeLaunch" not in body
        assert "Process.Start" not in body

    # CapRefusal rules: non-agent empty; agent refused at Seats() >= MaxWorkers; MaxWorkers = 2.
    assert "MaxWorkers = 2" in t
    cap_bodies = _csharp_method_bodies(t, "public static string CapRefusal(")
    assert len(cap_bodies) == 1
    _, cap_body = cap_bodies[0]
    assert 'string.Equals(mode' in cap_body or 'Equals(mode' in cap_body
    assert 'return ""' in cap_body or 'return "";' in cap_body
    assert "n >= MaxWorkers" in cap_body or "Seats() >= MaxWorkers" in cap_body

    # StartWorker (4-arg env path) calls the six-argument Launch overload.
    assert "WorkerLauncher.Launch(root, mode, mid, agent ?? \"\", childEnv, out err)" in t or (
        "WorkerLauncher.Launch(root, mode, mid, agent" in t and "childEnv" in t
    )


def test_mrb2602_ensure_report_only():
    ens = _read(ENSURE)
    assert "FR #3180" in ens or "report-only" in ens.lower()
    assert "Measure-BobTrayWorkerSeats -Procs" in ens
    assert "$DryRun" in ens
    assert "Set-Content" not in ens
    assert "Move-Item" not in ens or "req-" not in ens


def test_mrb2602_irc_lost_exit_3_and_docs_skill():
    assert "EXIT_IRC_LOST = 3" in _read(WORKER_PY)
    post = _read(POST)
    assert "FR #3180" in post and "manual only" in post.lower()
    skill = _read(SKILL)
    assert "FR #3180" in skill
    assert "manual only" in skill.lower()
    assert "HealWorkerSeats" not in skill
