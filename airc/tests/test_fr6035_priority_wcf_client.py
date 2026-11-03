"""FR #6035: Priority WCF SOAP client — offline, fake SOAP, no WINRUN/SDK/OData."""
from __future__ import annotations

import inspect
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import airc_console as ac
import airc_priority as ap
import priority_wcf as wcf
from airc_auth_helpers import ops_auth


def _secret() -> str:
    return "FAKE_" + "WCF" + "TOKEN" + "99"


def _inst(**extra):
    row = {
        "url": "https://priority.example.invalid",
        "user": "api-user",
        "credentialTarget": "PriorityWeb/example-dev",
    }
    row.update(extra)
    return row


def _ok_body(op: str, inner: str = "ok") -> str:
    return (
        '<?xml version="1.0"?>'
        f'<s:Envelope xmlns:s="{wcf.SOAP_NS}">'
        f"<s:Body><{op}Response xmlns=\"{wcf.TEMPURI}\">"
        f"<{op}Result>{inner}</{op}Result>"
        f"</{op}Response></s:Body></s:Envelope>"
    )


def _fault_body(msg: str = "nope") -> str:
    return (
        f'<s:Envelope xmlns:s="{wcf.SOAP_NS}"><s:Body>'
        f"<s:Fault><faultcode>s:Client</faultcode>"
        f"<faultstring>{msg}</faultstring></s:Fault>"
        "</s:Body></s:Envelope>"
    )


def test_fr6035_endpoint_from_url_and_override():
    assert wcf.wcf_endpoint(_inst()) == (
        "https://priority.example.invalid/wcf/wcf/Service.svc"
    )
    assert (
        wcf.wcf_endpoint(_inst(wcfUrl="https://override.example/Service.svc"))
        == "https://override.example/Service.svc"
    )
    assert wcf.wcf_endpoint({}) == ""


def test_fr6035_envelope_soapaction_usernametoken():
    secret = _secret()
    env = wcf.build_envelope("GetVersion", user="api-user", password=secret)
    assert 'xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"' in env
    assert "UsernameToken" in env
    assert "api-user" in env
    assert secret in env
    assert wcf.soap_action("ProcStart") == "http://tempuri.org/IWCFService/ProcStart"


def test_fr6035_direct_and_relay_vs_fake_http():
    secret = _secret()
    captured: list[tuple[str, dict, bytes]] = []

    def fake_post(url, data, headers, timeout_s=30.0):
        captured.append((url, headers, data))
        return 200, _ok_body("GetVersion", "21.1")

    for mode in ("direct", "relay"):
        c = wcf.PriorityWcfClient(
            _inst(),
            mode=mode,
            passed_password=secret,
            http_post=fake_post,
        )
        out = c.get_version()
        assert out["ok"] is True
        assert out["via"] == mode
        assert "21.1" in out["body"]
    url, headers, data = captured[0]
    assert url.endswith("/wcf/wcf/Service.svc")
    assert headers["SOAPAction"] == '"http://tempuri.org/IWCFService/GetFileVersion"'
    assert secret.encode("utf-8") in data
    assert "UsernameToken" in data.decode("utf-8")


def test_fr6035_proc_ops_and_fault_and_auth():
    secret = _secret()

    def start_post(url, data, headers, timeout_s=30.0):
        assert "FORMPREP" in data.decode("utf-8")
        assert headers["SOAPAction"] == '"http://tempuri.org/IWCFService/ProcStartMob"'
        return 200, _ok_body("ProcStart", "SESS1")

    c = wcf.PriorityWcfClient(
        _inst(), passed_password=secret, http_post=start_post
    )
    out = c.proc_start(typ="P", ename="FORMPREP")
    assert out["ok"] and "SESS1" in out["body"]

    def fault_post(url, data, headers, timeout_s=30.0):
        return 200, _fault_body("bad session")

    c2 = wcf.PriorityWcfClient(
        _inst(), passed_password=secret, http_post=fault_post
    )
    bad = c2.proc_continue("SESS1")
    assert bad["ok"] is False
    assert bad["error"] == wcf.SOAP_FAULT

    def auth_post(url, data, headers, timeout_s=30.0):
        return 401, "no"

    c3 = wcf.PriorityWcfClient(
        _inst(), passed_password=secret, http_post=auth_post
    )
    denied = c3.general_companies()
    assert denied["error"] == wcf.WCF_AUTH_FAILED


def test_fr6035_optional_not_installed_not_configured():
    c = wcf.PriorityWcfClient({}, allowlist_present=False, passed_password=_secret())
    assert c.get_version()["error"] == wcf.PRIORITY_NOT_INSTALLED
    c2 = wcf.PriorityWcfClient({}, passed_password=_secret())
    assert c2.get_version()["error"] == wcf.PRIORITY_NOT_CONFIGURED
    c3 = wcf.PriorityWcfClient(_inst(), passed_password=_secret())
    assert c3.call("Login")["error"] == wcf.WCF_BAD_OP


def test_fr6035_no_winrun_sdk_odata_in_module():
    src = Path(wcf.__file__).read_text(encoding="utf-8")
    code = "\n".join(
        ln for ln in src.splitlines() if not ln.lstrip().startswith(("#", '"""', "'''"))
    )
    assert "WINACTIV" not in code
    assert "priority-web-sdk" not in code
    assert "odata/" not in code.lower()
    assert "from airc_winrun" not in code
    assert inspect.signature(wcf.PriorityWcfClient.call)


def test_fr6035_secret_never_in_result_or_logs():
    secret = _secret()

    def boom(url, data, headers, timeout_s=30.0):
        raise ConnectionError("down")

    out = wcf.PriorityWcfClient(
        _inst(), passed_password=secret, http_post=boom
    ).get_version()
    assert secret not in str(out)
    assert "password" not in str(out).lower() or "password=" not in str(out).lower()
    red = wcf.redact(f"user=x password={secret}", secret)
    assert secret not in red
    assert "***" in red


def test_fr6035_credman_fetcher_used():
    secret = _secret()
    seen = []

    def fetch(target):
        seen.append(target)
        return secret

    def fake_post(url, data, headers, timeout_s=30.0):
        assert secret.encode() in data
        return 200, _ok_body("GetVersion")

    out = wcf.PriorityWcfClient(
        _inst(), cred_fetcher=fetch, http_post=fake_post
    ).get_version()
    assert out["ok"]
    assert seen == ["PriorityWeb/example-dev"]


def test_fr6035_live_http_server_both_modes():
    secret = _secret()
    hits = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n)
            hits.append((self.path, self.headers.get("SOAPAction"), body))
            payload = _ok_body("GetVersion", "live-fake").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/xml")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *a):
            return

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    th = Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/wcf/wcf/Service.svc"
        inst = {"wcfUrl": url, "user": "api-user"}
        for mode in ("direct", "relay"):
            out = wcf.PriorityWcfClient(
                inst, mode=mode, passed_password=secret
            ).get_version()
            assert out["ok"] is True
            assert out["via"] == mode
    finally:
        srv.shutdown()
        srv.server_close()
    assert hits
    assert "GetFileVersion" in (hits[0][1] or "")


def test_fr6035_priority_wcf_verb_parse_and_run():
    secret = _secret()
    p = wcf.parse_priority_wcf_command(
        "id=aabb6035 PRIORITY wcf GetVersion example-dev"
    )
    assert p["op"] == "GetFileVersion"
    assert p["instance"] == "example-dev"
    assert ap.parse_priority_usage("PRIORITY wcf GetVersion x") is None

    def fake_post(url, data, headers, timeout_s=30.0):
        return 200, _ok_body("GetVersion", "v")

    out = wcf.run_priority_wcf(
        "PRIORITY wcf getversion url=https://priority.example.invalid user=api-user",
        passed_password=secret,
        http_post=fake_post,
        mode="direct",
    )
    assert out["ok"]
    assert out["action"] == "wcf"


def test_fr6035_console_not_installed():
    auth = ops_auth("bob-flamingo", channel="#flamingo")
    root = Path.cwd()  # unused; install_root empty config
    core = ac.AircConsoleCore(
        machine="flamingo",
        auth=auth,
        nick="flamingo_console",
        install_root=str(Path(__file__).resolve().parents[2] / "no-such-airc-root"),
    )
    hr = core.handle_raw(
        ":bob-flamingo!u@h PRIVMSG flamingo_console :id=aa006035 PRIORITY wcf GetVersion x"
    )
    assert hr is not None
    text = hr.reply or ""
    assert "priority_not_installed" in text
    assert _secret() not in text
    assert "DONE id=aa006035" in text
