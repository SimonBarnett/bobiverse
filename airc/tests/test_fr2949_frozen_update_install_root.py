"""FR #2949: frozen airc.exe UPDATE must not look under _MEI for the updater."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import airc_console as ac
import airc_console_service as svc


def test_fr2949_schedule_finds_updater_under_install_root_scripts(tmp_path, monkeypatch):
    root = tmp_path / "install"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    upd = scripts / "Update-BobiverseService.ps1"
    upd.write_text("param($Product,$Mode)\nexit 0\n", encoding="utf-8")

    # Simulate frozen: __file__-relative script path would be wrong / missing.
    mei = tmp_path / "_MEIdeadbeef"
    mei.mkdir()
    fake_mod = mei / "airc_console.py"
    fake_mod.write_text("# fake", encoding="utf-8")

    recorded: list[list[str]] = []

    def fake_run(args, **kwargs):
        recorded.append(list(args))
        return mock.Mock(returncode=0, stdout="self-update: result=scheduled-nospawn\n", stderr="")

    monkeypatch.setattr(ac.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(mei), raising=False)
    monkeypatch.setattr(sys, "executable", str(root / "airc" / "airc.exe"))
    (root / "airc").mkdir(parents=True, exist_ok=True)
    (root / "airc" / "airc.exe").write_bytes(b"MZ")

    result = ac.schedule_fleet_update(
        "airc",
        "0.1.25",
        install_root=str(root),
        no_spawn=True,
    )
    assert result.ok, result.reply_line()
    assert result.status != "updater-missing"
    assert "updater-missing" not in result.reply_line()
    # Check mode argv must point at real install scripts, not _MEI.
    assert recorded
    joined = " ".join(recorded[0])
    assert str(upd) in joined or "Update-BobiverseService.ps1" in joined
    assert "_MEI" not in joined


def test_fr2949_schedule_frozen_re_resolves_when_install_root_is_mei(tmp_path, monkeypatch):
    """Service used to pass Path(__file__).parents[1] == _MEI*; must still find updater."""
    root = tmp_path / "install"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    upd = scripts / "Update-BobiverseService.ps1"
    upd.write_text("param($Product,$Mode)\nexit 0\n", encoding="utf-8")
    mei = tmp_path / "_MEI0000a6bc2"
    mei.mkdir()
    exe = root / "airc" / "airc.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ")

    recorded: list[list[str]] = []

    def fake_run(args, **kwargs):
        recorded.append(list(args))
        return mock.Mock(returncode=0, stdout="self-update: result=scheduled-nospawn\n", stderr="")

    monkeypatch.setattr(ac.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(mei), raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))

    result = ac.schedule_fleet_update(
        "airc",
        "0.1.25",
        install_root=str(mei),  # bogus frozen parents[1]
        no_spawn=True,
    )
    assert result.ok, result.reply_line()
    assert "updater-missing" not in result.reply_line()
    assert recorded
    assert str(upd) in " ".join(recorded[0])


def test_fr2949_service_install_root_uses_resolve_helper(tmp_path, monkeypatch):
    """AircConsoleService must not hard-code Path(__file__).parents[1] for UPDATE."""
    text = Path(svc.__file__).read_text(encoding="utf-8")
    assert "resolve_airc_install_root()" in text
    # The FR #77 UPDATE install_root assignment must call the frozen-aware helper.
    assert "install_root = str(Path(__file__).resolve().parents[1])" not in text


def test_fr2949_update_missing_still_action_update_not_shell():
    """UPDATE body must never fall through to shell/pipe even when updater-missing."""
    def scheduler(product, version=None, **kwargs):
        return ac.UpdateScheduleResult(
            False, "updater-missing", detail=r"C:\Windows\Temp\_MEI\Update-BobiverseService.ps1",
            product=product, version=version,
        )

    auth = ac.AuthPolicy(operators={"bob-marchhare"}, machine="marchhare")
    core = ac.AircConsoleCore(
        machine="marchhare",
        auth=auth,
        nick="marchhare_console",
        update_scheduler=scheduler,
        shell_runner=mock.Mock(),
    )
    r = core.handle_raw(":bob-marchhare!u@h PRIVMSG marchhare_console :UPDATE airc 0.1.25")
    assert r is not None
    assert r.action == "update"
    assert "updater-missing" in (r.reply or "")
    core.shell_runner.start.assert_not_called()
