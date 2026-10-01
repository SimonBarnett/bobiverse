"""Chair OPER on connect + channel +o upkeep + loud LIST/oper status (v0.1.15)."""
import sys
import time
from types import SimpleNamespace

import pytest

import chair_oper as co
import irc_agent
import registered_machines as rm


# ------------------------------------------------------------------ credentials (never printed)
def test_oper_file_formats():
    assert co.parse_oper_file("Ergo oper 'admin' password\n\nTOKENTOKEN\n\n/OPER admin TOKENTOKEN\n/NS SAREGISTER simon <x>") == ("admin", "TOKENTOKEN")
    assert co.parse_oper_file("justone") == ("admin", "justone")
    assert co.parse_oper_file("/OPER <name> <password>") is None
    assert co.parse_oper_file("") is None


def test_provision_roundtrip_and_no_secret_in_status(tmp_path, capsys):
    cfg = tmp_path / "config"
    f = tmp_path / "ergo-oper-admin.txt"
    f.write_text("hdr\n\n/OPER admin P4ssw0rd-Value-Here\n", encoding="utf-8")
    res = co.provision(cfg, oper_file=str(f))
    assert res["status"] == "provisioned" and res["name"] == "admin"
    assert "P4ssw0rd" not in repr(res)
    assert co.load_credentials(co.cred_path(cfg)) == ("admin", "P4ssw0rd-Value-Here")
    # on Windows the file is DPAPI-protected (not plaintext on disk)
    raw = co.cred_path(cfg).read_bytes()
    if sys.platform == "win32":
        assert b"P4ssw0rd" not in raw and raw.startswith(b"AIRC2")
    # re-provision without args keeps the existing credential
    again = co.provision(cfg)
    assert again["status"] == "kept" and "P4ssw0rd" not in repr(again)


def test_provision_param_path_and_missing(tmp_path):
    cfg = tmp_path / "config"
    assert co.provision(cfg, profiles=[tmp_path / "nobody"])["status"] == "missing"
    res = co.provision(cfg, name="jeeves", password="pw-1234567890")
    assert res["source"] == "parameter" and co.load_credentials(co.cred_path(cfg)) == ("jeeves", "pw-1234567890")
    with pytest.raises(ValueError):
        co.write_credentials(tmp_path / "x", "a", "b\nc")


def test_provision_discovers_desktop_file(tmp_path):
    prof = tmp_path / "Administrator"
    (prof / "Desktop").mkdir(parents=True)
    (prof / "Desktop" / "ergo-oper-admin.txt").write_text("/OPER admin abcdefghijkl", encoding="utf-8")
    res = co.provision(tmp_path / "cfg", profiles=[prof])
    assert res["status"] == "provisioned" and res["source"].endswith("ergo-oper-admin.txt")


def test_cli_prints_status_only(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("BOB_OPER_PASSWORD", "env-pass-123456")
    rc = co.main(["provision", "--config-dir", str(tmp_path / "c"), "--name", "admin"])
    out = capsys.readouterr().out
    assert rc == 0 and "provisioned" in out and "env-pass-123456" not in out


# ------------------------------------------------------------------ wire parsing
def test_umode_and_names_and_mode_parsers():
    assert co.umode_has_o("+iZo") and co.umode_has_o(":+o") and not co.umode_has_o("+i") and not co.umode_has_o("+o-o")
    assert co.names_has_op(["353", "Jeeves", "=", "#bobiverse"], "@Jeeves +bob-x carol", "Jeeves") == ("#bobiverse", True)
    assert co.names_has_op(["353", "Jeeves", "=", "#bobiverse"], "Jeeves bob-x", "Jeeves") == ("#bobiverse", False)
    assert co.mode_changes_for(["MODE", "#c", "+ov", "Jeeves", "bob"], "jeeves") == [("#c", "o", True)]
    assert co.mode_changes_for(["MODE", "#c", "-o", "Jeeves"], "Jeeves") == [("#c", "o", False)]
    assert co.mode_changes_for(["MODE", "#c", "+o", "someoneelse"], "Jeeves") == []
    assert co.mode_changes_for(["MODE", "Jeeves", "+o"], "Jeeves") == []


# ------------------------------------------------------------------ chair state machine
class _FakeChair:
    def __init__(self, home, cfg):
        self.args = SimpleNamespace(chair=True)
        self.home = home
        self.live_nick = "Jeeves"
        self.channels = ["#bobiverse", "#marchhare", "#win-mpre8vi4u6u"]
        self.sent = []
        self.joined = SimpleNamespace(is_set=lambda: True)
        self._cs_collector = None
        self._cs_sent_at = 0.0
        self._cs_force = False
        self._cs_fail_at = 0.0
        self._cs_list_status = "unknown"
        self._oper_state = "off"
        self._oper_name = ""
        self._oper_done = __import__("threading").Event()
        self._chan_op = {}
        self._op_try_at = {}
        self._chair_status_at = 0.0
        self._chair_status_last = ""
        self.cfg = cfg

    def send(self, line):
        self.sent.append(line)
        if line.startswith("OPER "):
            self.on_oper_sent()

    on_oper_sent = lambda self: None  # noqa: E731

    def _digest_home(self):
        return self.home

    _chair_reset_session = irc_agent.Client._chair_reset_session
    _chair_oper_on_connect = irc_agent.Client._chair_oper_on_connect
    _on_oper_numeric = irc_agent.Client._on_oper_numeric
    _on_chair_channel_line = irc_agent.Client._on_chair_channel_line
    _ensure_chan_ops = irc_agent.Client._ensure_chan_ops
    _chair_status_line = irc_agent.Client._chair_status_line
    _chair_log_status = irc_agent.Client._chair_log_status
    _cs_ttl_s = irc_agent.Client._cs_ttl_s
    _maybe_chanserv_sync = irc_agent.Client._maybe_chanserv_sync
    _on_chanserv_notice = irc_agent.Client._on_chanserv_notice
    _apply_chanserv_channels = irc_agent.Client._apply_chanserv_channels


@pytest.fixture
def chair(tmp_path, monkeypatch):
    cfg = tmp_path / "config"
    monkeypatch.setenv("BOB_CONFIG_DIR", str(cfg))
    monkeypatch.delenv("BOB_OPER_FILE", raising=False)
    return _FakeChair(tmp_path / "home", cfg)


def _logs(monkeypatch):
    out = []
    monkeypatch.setattr(irc_agent, "info", lambda m: out.append(m))
    return out


def test_no_credentials_is_loud_and_does_not_send_oper(chair, monkeypatch):
    logs = _logs(monkeypatch)
    chair._chair_oper_on_connect()
    assert chair._oper_state == "nocred" and not any(s.startswith("OPER") for s in chair.sent)
    assert any("OPER SKIPPED" in m and "NOT an IRC operator" in m for m in logs)


def test_oper_sent_on_connect_and_381_confirms(chair, monkeypatch):
    logs = _logs(monkeypatch)
    co.provision(chair.cfg, name="admin", password="pw-secret-0123456")
    chair.on_oper_sent = lambda: chair._on_oper_numeric("381", ["381", "Jeeves"], "You are now an IRC operator")
    chair._chair_oper_on_connect()
    assert chair.sent == ["OPER admin pw-secret-0123456"]
    assert chair._oper_state == "ok"
    assert any("OPER OK: 381" in m for m in logs)
    assert not any("pw-secret" in m for m in logs)  # never logged


def test_oper_failure_491_is_loud(chair, monkeypatch):
    logs = _logs(monkeypatch)
    co.provision(chair.cfg, name="admin", password="wrongpw-0123456789")
    chair.on_oper_sent = lambda: chair._on_oper_numeric("491", ["491", "Jeeves"], "Password incorrect")
    chair._chair_oper_on_connect()
    assert chair._oper_state == "failed"
    assert any("OPER FAILED" in m and "NOT an operator" in m for m in logs)
    assert not any("wrongpw" in m for m in logs)


def test_oper_timeout_is_not_oper(chair, monkeypatch):
    logs = _logs(monkeypatch)
    co.provision(chair.cfg, name="admin", password="pw-0123456789abc")
    monkeypatch.setattr(chair._oper_done, "wait", lambda t=None: False)
    chair._chair_oper_on_connect()
    assert chair._oper_state == "failed" and any("no reply" in m for m in logs)


def test_user_mode_plus_o_also_confirms(chair, monkeypatch):
    _logs(monkeypatch)
    chair._oper_state = "pending"
    chair._on_oper_numeric("MODE", ["MODE", "Jeeves", ":+o"], "")  # server MODE for own nick
    assert chair._oper_state == "ok"
    chair._oper_state = "pending"
    chair._on_oper_numeric("221", ["221", "Jeeves", "+iZo"], "")
    assert chair._oper_state == "ok"


def test_samode_plus_o_in_every_channel_when_oper(chair, monkeypatch):
    logs = _logs(monkeypatch)
    chair._oper_state = "ok"
    chair._on_chair_channel_line("353", ["353", "Jeeves", "=", "#bobiverse"], "@Jeeves bob")
    chair._ensure_chan_ops()
    assert "SAMODE #bobiverse +o Jeeves" not in chair.sent
    assert "SAMODE #marchhare +o Jeeves" in chair.sent and "SAMODE #win-mpre8vi4u6u +o Jeeves" in chair.sent
    n = len(chair.sent)
    chair._ensure_chan_ops()  # throttled: no spam
    assert len(chair.sent) == n
    # server confirms the mode -> tracked, status loud/OK once all ops
    for c in ("#marchhare", "#win-mpre8vi4u6u"):
        chair._on_chair_channel_line("MODE", ["MODE", c, "+o", "Jeeves"], "")
    assert all(chair._chan_op.get(c.lower()) for c in chair.channels)
    chair._chair_log_status(force=True)
    assert any(m.startswith("INFO chair-status oper=ok") and "NOT-op-in=-" in m for m in logs)


def test_not_oper_falls_back_to_chanserv_op_and_warns(chair, monkeypatch):
    logs = _logs(monkeypatch)
    chair._oper_state = "nocred"
    chair._ensure_chan_ops()
    assert "PRIVMSG ChanServ :OP #marchhare" in chair.sent and not any(s.startswith("SAMODE") for s in chair.sent)
    assert any(m.startswith("WARN chair-status oper=nocred") for m in logs)


def test_new_channel_from_chanserv_sync_gets_op(chair, monkeypatch):
    _logs(monkeypatch)
    chair._oper_state = "ok"
    chair.channels.append("#newbox")
    chair._ensure_chan_ops()
    assert "SAMODE #newbox +o Jeeves" in chair.sent


def test_chair_loses_op_then_regains(chair, monkeypatch):
    _logs(monkeypatch)
    chair._oper_state = "ok"
    chair._on_chair_channel_line("MODE", ["MODE", "#bobiverse", "-o", "Jeeves"], "")
    assert chair._chan_op["#bobiverse"] is False
    chair._ensure_chan_ops()
    assert "SAMODE #bobiverse +o Jeeves" in chair.sent


def test_list_denied_is_loud_with_exact_config_hint(chair, monkeypatch):
    logs = _logs(monkeypatch)
    chair._oper_state = "ok"
    chair._oper_name = "admin"
    chair._maybe_chanserv_sync()
    chair._on_chanserv_notice("Insufficient privileges")
    assert chair._cs_list_status == "denied"
    msg = next(m for m in logs if "LIST DENIED" in m)
    assert msg.startswith("ERROR") and 'capabilities' in msg and '- "chanreg"' in msg and "admin" in msg
    assert "oper=ok" in chair._chair_status_line() and "chanserv-list=denied" in chair._chair_status_line()


def test_list_ok_when_oper_has_chanreg(chair, monkeypatch):
    logs = _logs(monkeypatch)
    chair._oper_state = "ok"
    rm.save_registered(chair.home, set())
    chair._maybe_chanserv_sync()
    for ln in ("*** ChanServ LIST ***", " #bobiverse", " #marchhare", " #win-mpre8vi4u6u", "*** End of ChanServ LIST ***"):
        chair._on_chanserv_notice(ln)
    assert chair._cs_list_status == "ok" and any("chanserv LIST OK" in m for m in logs)
    assert rm.load_registered(chair.home) == {"marchhare", "win-mpre8vi4u6u"}


def test_reconnect_resets_session_state(chair):
    chair._oper_state = "ok"
    chair._chan_op = {"#bobiverse": True}
    chair._cs_list_status = "ok"
    chair._chair_reset_session()
    assert chair._oper_state == "off" and chair._chan_op == {} and chair._cs_list_status == "unknown"


def test_session_sends_oper_before_join_in_source():
    src = open(irc_agent.__file__, encoding="utf-8").read()
    ses = src.split("    def session(self)", 1)[1]
    assert ses.index("_chair_oper_on_connect()") < ses.index('self.send("JOIN " + ch)')
    rd = src.split("    def reader(self)", 1)[1]
    assert "_on_oper_numeric" in rd and "_on_chair_channel_line" in rd


def test_installer_provisions_oper_without_prompt():
    from pathlib import Path
    t = (Path(irc_agent.__file__).parent / "Install-Jeeves.ps1").read_text(encoding="utf-8-sig")
    assert "chair_oper.py" in t and "'provision'" in t and "$OperFile" in t and "$OperName" in t
    assert "Read-Host" not in t.split("chair_oper.py", 1)[1].split("BobCallback", 1)[0]
