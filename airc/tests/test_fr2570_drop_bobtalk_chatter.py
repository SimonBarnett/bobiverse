"""FR #2570 follow-up: bobtalk-only chatter must not reach PowerShell."""
from __future__ import annotations

import airc_console as ac
import airc_jobs as jobs
from repo_layout import ROOT


def test_sanitize_drops_bobtalk_presence_only():
    assert ac.sanitize_console_operator_text(
        "@marchhare_console marchhare here. weekly=26."
    ) == ""
    assert ac.sanitize_console_operator_text(
        "@marchhare_console marchhare here. weekly=26"
    ) == ""
    # Still a splat nick with no Heard: payload
    assert ac.sanitize_console_operator_text("@someone_console hi") == ""


def test_sanitize_keeps_heard_status_and_shell_with_id():
    assert ac.sanitize_console_operator_text(
        "@marchhare_console marchhare here. weekly=26. Heard: STATUS"
    ) == "STATUS"
    assert ac.sanitize_console_operator_text(
        "@marchhare_console marchhare here. weekly=26. Heard: id=aabbccdd STATUS"
    ) == "id=aabbccdd STATUS"
    assert ac.sanitize_console_operator_text("id=deadbeef hostname") == "id=deadbeef hostname"


def test_handle_raw_drops_bobtalk_chatter_without_shell(tmp_path):
    replies: list[str] = []
    started: list[str] = []

    class _Runner:
        def start(self, nick: str, cmd: str) -> None:
            started.append(cmd)

    for name in ("bob", "airc", "jeeves"):
        d = tmp_path / name
        d.mkdir()
        (d / "VERSION").write_text("1\n", encoding="utf-8")
    store = jobs.JobStore(tmp_path / "home")
    proto = jobs.JobProtocol(
        store,
        on_reply=lambda n, line: replies.append(line),
        ai_root=tmp_path,
        machine="tm",
        airc_running=True,
    )
    auth = ac.AuthPolicy(operators={"bob-tm"}, machine="tm")
    core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        sessions=ac.ConsoleSessionManager(on_output=None),
        nick="tm_console",
        job_protocol=proto,
        shell_runner=_Runner(),
    )
    hr = core.handle_raw(
        ":bob-tm!u@h PRIVMSG tm_console :@tm_console marchhare here. weekly=27."
    )
    assert hr is not None and hr.action == "empty"
    assert started == []
    assert replies == []


def test_invoke_status_still_pins_id_on_main_tip():
    t = (ROOT / "airc" / "scripts" / "Invoke-AircRemote.ps1").read_text(encoding="utf-8-sig")
    assert "id={0} STATUS" in t
    assert "'Status'" in t


def test_mrb2573_keeps_powershell_array_at_paren():
    """MRB #2573: leading @(...) must not be dropped as a nick mention."""
    cmd = "@('a','b') | ForEach-Object { $_ }"
    assert ac.sanitize_console_operator_text(cmd) == cmd
    hs = '@"\nhi\n"@'
    assert ac.sanitize_console_operator_text(hs) == hs


def test_mrb2573_no_unreachable_sanitize_tail():
    """MRB #2573: sanitize must not leave dead duplicate Heard:/bobtalk block."""
    src = (ROOT / "airc" / "scripts" / "airc_console.py").read_text(encoding="utf-8")
    fn = src[src.index("def sanitize_console_operator_text") : src.index("def parse_shell_request")]
    assert fn.count("_HEARD_PAYLOAD_RE.search") == 1
    assert fn.count("_BOBTALK_PREFIX_RE.match") == 1
    assert fn.rstrip().endswith("return raw")

