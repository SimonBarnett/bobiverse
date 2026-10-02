"""FR #88: bob_git_hook announce gate stays strict; diagnose dead listeners."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "tools" / "bob_git_hook.py"

spec = importlib.util.spec_from_file_location("bob_git_hook", HOOK)
hook = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["bob_git_hook"] = hook
spec.loader.exec_module(hook)


def test_default_log_paths_include_legacy_and_bob_homes(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("BOB_HOME", raising=False)
    monkeypatch.delenv("BOB_INSTALL_ROOT", raising=False)
    paths = [Path(p) for p in hook.default_log_paths()]
    names = [p.as_posix() for p in paths]
    assert any(n.endswith(".agentic-irc-bobiverse/irc.log") for n in names)
    assert any(n.endswith(".bobiverse/irc.log") for n in names)
    assert any(n.endswith(".agentic-irc-gitannounce/irc.log") for n in names)


def test_default_log_paths_include_bob_home_env(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    bob_home = tmp_path / "bob-home"
    monkeypatch.setenv("BOB_HOME", str(bob_home))
    paths = [Path(p) for p in hook.default_log_paths()]
    assert bob_home / "irc.log" in paths


def test_announce_seen_requires_jeeves_privmsg(tmp_path):
    log = tmp_path / "irc.log"
    log.write_text(
        ":noise!x@y PRIVMSG #bobiverse :GIT ping SimonBarnett/x\n"
        ":Jeeves!j@h PRIVMSG #bobiverse :GIT ping SimonBarnett/plan-smoke-20261002\n",
        encoding="utf-8",
    )
    hit = hook.announce_seen("GIT ping SimonBarnett/plan-smoke-20261002", [log])
    assert hit is not None and hit.startswith(":Jeeves!")
    assert hook.announce_seen("GIT ping SimonBarnett/missing", [log]) is None


def test_diagnose_nickname_reserved_when_log_is_only_collisions(tmp_path):
    log = tmp_path / "irc.log"
    lines = []
    for _ in range(30):
        lines.append(":irc.ntsa.uk 433 * bob-marchhare :Nickname is reserved by a different account")
        lines.append(":irc.ntsa.uk FAIL NICK NICKNAME_RESERVED bob-marchhare :Nickname is reserved")
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    diag = hook.diagnose_listener_logs([log])
    assert diag is not None
    assert "NICKNAME_RESERVED" in diag
    assert "bob-marchhare" in diag or "bob-" in diag


def test_diagnose_clean_when_jeeves_traffic_present(tmp_path):
    log = tmp_path / "irc.log"
    log.write_text(
        ":Jeeves!j@h PRIVMSG #bobiverse :GIT ping SimonBarnett/x\n"
        ":Bob-marchhare!b@h PRIVMSG #bobiverse :hello\n",
        encoding="utf-8",
    )
    assert hook.diagnose_listener_logs([log]) is None


def test_fail_announce_message_mentions_listener_repair(tmp_path):
    msg = hook.format_announce_fail(
        missing=["GIT ping SimonBarnett/plan-smoke-20261002"],
        logs=[tmp_path / "irc.log"],
        listener_diag=(
            "NICKNAME_RESERVED loop for bob-marchhare — Start-BobiverseGitAnnounceListen.ps1; "
            "do not weaken the announce gate."
        ),
    )
    assert "FAIL" in msg
    assert "NICKNAME_RESERVED" in msg
    assert "do not weaken" in msg.lower()
    assert "Start-BobiverseGitAnnounceListen" in msg
