"""Priority WCF SOAP client (FR #6035). Offline-tested; no WINRUN / web SDK / OData.

Endpoint: ``{serverUrl}/wcf/wcf/Service.svc`` unless ``wcfUrl`` / ``wcfPath``
overrides. SOAP 1.1 ``IWCFService``, SOAPAction
``http://tempuri.org/IWCFService/<Op>``. Every call carries a WS-Security
UsernameToken. Credentials: passed-in (TLS/DCC) then CredMan (FR #5659).
Never log, argv, IRC, or dump the password.
"""
from __future__ import annotations

import re
import ssl
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
WSSE_NS = (
    "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
)
TEMPURI = "http://tempuri.org/"
SOAP_ACTION_TMPL = "http://tempuri.org/IWCFService/{op}"
DEFAULT_WCF_PATH = "/wcf/wcf/Service.svc"

OPS = ("GetVersion", "GeneralCompanies", "ProcStart", "ProcContinue", "ProcEnd")

PRIORITY_NOT_INSTALLED = "priority_not_installed"
PRIORITY_NOT_CONFIGURED = "priority_not_configured"
WCF_AUTH_FAILED = "wcf_auth_failed"
SOAP_FAULT = "soap_fault"
WCF_UNREACHABLE = "wcf_unreachable"
WCF_BAD_OP = "wcf_bad_op"

_PASS_RE = re.compile(r"(?i)(password|passwd|pwd|secret)\s*[:=]\s*\S+")


def wcf_endpoint(instance: dict | None) -> str:
    """Derive WCF URL from instance server URL; optional override only."""
    inst = instance if isinstance(instance, dict) else {}
    override = str(inst.get("wcfUrl") or inst.get("wcf_url") or "").strip()
    if override:
        return override
    base = str(inst.get("url") or inst.get("serverUrl") or inst.get("server_url") or "").strip()
    if not base:
        return ""
    path = str(inst.get("wcfPath") or inst.get("wcf_path") or DEFAULT_WCF_PATH).strip()
    if not path.startswith("/"):
        path = "/" + path
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def _xml_escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_envelope(
    op: str,
    *,
    user: str,
    password: str,
    body_fields: dict[str, Any] | None = None,
) -> str:
    """SOAP 1.1 envelope with UsernameToken. Caller must not log the result."""
    name = str(op or "").strip()
    fields = body_fields or {}
    inner = "".join(
        f"<{k}>{_xml_escape(v)}</{k}>" for k, v in fields.items() if v is not None
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<s:Envelope xmlns:s="{SOAP_NS}">'
        "<s:Header>"
        f'<wsse:Security xmlns:wsse="{WSSE_NS}">'
        "<wsse:UsernameToken>"
        f"<wsse:Username>{_xml_escape(user)}</wsse:Username>"
        f'<wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/'
        f'oasis-200401-wss-username-token-profile-1.0#PasswordText">'
        f"{_xml_escape(password)}</wsse:Password>"
        "</wsse:UsernameToken>"
        "</wsse:Security>"
        "</s:Header>"
        "<s:Body>"
        f'<{name} xmlns="{TEMPURI}">{inner}</{name}>'
        "</s:Body>"
        "</s:Envelope>"
    )


def soap_action(op: str) -> str:
    return SOAP_ACTION_TMPL.format(op=str(op).strip())


def redact(text: str, secret: str = "") -> str:
    s = str(text or "")
    if secret:
        s = s.replace(secret, "***")
    return _PASS_RE.sub(r"\1=***", s)


def parse_soap_response(xml_text: str) -> dict[str, Any]:
    raw = str(xml_text or "")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return {"ok": False, "error": SOAP_FAULT, "detail": "bad_xml"}
    fault = root.find(f".//{{{SOAP_NS}}}Fault")
    if fault is None:
        # Unqualified Fault (some stacks).
        fault = root.find(".//{*}Fault")
    if fault is not None:
        code = "".join(fault.findtext(".//{*}faultcode") or fault.findtext(".//{*}Code") or "")
        msg = "".join(fault.findtext(".//{*}faultstring") or fault.findtext(".//{*}Reason") or "")
        return {
            "ok": False,
            "error": SOAP_FAULT,
            "fault_code": redact(code),
            "fault_string": redact(msg)[:160],
        }
    body = root.find(f".//{{{SOAP_NS}}}Body")
    text = ""
    if body is not None:
        text = "".join(body.itertext()).strip()
    return {"ok": True, "body": text[:4000], "via": "wcf"}


def _http_post(
    url: str,
    data: bytes,
    headers: dict[str, str],
    *,
    timeout_s: float = 30.0,
) -> tuple[int, str]:
    req = Request(url, data=data, headers=headers, method="POST")
    kw: dict[str, Any] = {"timeout": timeout_s}
    if str(url).lower().startswith("https://"):
        kw["context"] = ssl.create_default_context()
    try:
        with urlopen(req, **kw) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return int(e.code), body
    except URLError as e:
        raise ConnectionError(str(e.reason or e)) from e


class PriorityWcfClient:
    """Shared client for direct (SaaS) and relay (on-LAN airc) transports."""

    def __init__(
        self,
        instance: dict | None,
        *,
        mode: str = "direct",
        cred_fetcher: Callable[[str], str] | None = None,
        passed_password: str | None = None,
        http_post: Callable[..., tuple[int, str]] | None = None,
        allowlist_present: bool | None = None,
    ) -> None:
        self.instance = instance if isinstance(instance, dict) else {}
        self.mode = "relay" if str(mode).strip().lower() == "relay" else "direct"
        self._fetch = cred_fetcher
        self._passed = passed_password
        self._http_post = http_post or _http_post
        self._allowlist_present = allowlist_present

    def _secret(self) -> tuple[str, str | None]:
        if self._passed:
            return str(self._passed), None
        target = str(
            self.instance.get("credentialTarget")
            or self.instance.get("credential_target")
            or ""
        ).strip()
        if not target or self._fetch is None:
            return "", "no_cred"
        try:
            secret = self._fetch(target) or ""
        except Exception:  # noqa: BLE001
            return "", "no_cred"
        if not secret:
            return "", "no_cred"
        return str(secret), None

    def call(
        self,
        op: str,
        *,
        fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self._allowlist_present is False:
            return {"ok": False, "error": PRIORITY_NOT_INSTALLED, "via": "wcf"}
        name = str(op or "").strip()
        if name not in OPS:
            return {"ok": False, "error": WCF_BAD_OP, "op": name, "via": "wcf"}
        url = wcf_endpoint(self.instance)
        if not url:
            return {"ok": False, "error": PRIORITY_NOT_CONFIGURED, "via": "wcf"}
        user = str(self.instance.get("user") or "").strip()
        if not user:
            return {"ok": False, "error": PRIORITY_NOT_CONFIGURED, "via": "wcf"}
        secret, cred_err = self._secret()
        if cred_err:
            return {"ok": False, "error": cred_err, "via": "wcf"}
        to_redact = secret
        envelope = build_envelope(name, user=user, password=secret, body_fields=fields)
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f'"{soap_action(name)}"',
        }
        try:
            status, body = self._http_post(
                url, envelope.encode("utf-8"), headers, timeout_s=30.0
            )
        except ConnectionError:
            return {"ok": False, "error": WCF_UNREACHABLE, "via": self.mode}
        except Exception:  # noqa: BLE001
            return {"ok": False, "error": WCF_UNREACHABLE, "via": self.mode}
        finally:
            envelope = ""
            secret = ""
        if status in (401, 403):
            return {"ok": False, "error": WCF_AUTH_FAILED, "via": self.mode}
        parsed = parse_soap_response(body)
        parsed["op"] = name
        parsed["via"] = self.mode
        parsed["endpoint_ok"] = True
        if to_redact:
            for k, v in list(parsed.items()):
                if isinstance(v, str) and to_redact in v:
                    parsed[k] = redact(v, to_redact)
        return parsed

    def get_version(self) -> dict[str, Any]:
        return self.call("GetVersion")

    def general_companies(self) -> dict[str, Any]:
        return self.call("GeneralCompanies")

    def proc_start(
        self,
        *,
        typ: str,
        ename: str,
        debug: str = "0",
        repexec: str = "",
        avoidmessages: str = "1",
    ) -> dict[str, Any]:
        return self.call(
            "ProcStart",
            fields={
                "type": typ,
                "ename": ename,
                "debug": debug,
                "repexec": repexec,
                "avoidmessages": avoidmessages,
            },
        )

    def proc_continue(self, session: str) -> dict[str, Any]:
        return self.call("ProcContinue", fields={"session": session})

    def proc_end(self, session: str = "") -> dict[str, Any]:
        return self.call("ProcEnd", fields={"session": session} if session else None)


def client_for_instance(
    instance: dict | None,
    *,
    mode: str = "direct",
    **kw: Any,
) -> PriorityWcfClient:
    return PriorityWcfClient(instance, mode=mode, **kw)


_WCF_VERB_RE = re.compile(
    r"(?is)^(?:id=([0-9a-f]{8})\s+)?PRIORITY\s+wcf\s+(\S+)(?:\s+(.*))?$"
)
_KV_RE = re.compile(r"(\w+)=([^\s]+)")
_OP_ALIAS = {
    "getversion": "GetVersion",
    "version": "GetVersion",
    "generalcompanies": "GeneralCompanies",
    "companies": "GeneralCompanies",
    "procstart": "ProcStart",
    "proccontinue": "ProcContinue",
    "procend": "ProcEnd",
}
for _n in OPS:
    _OP_ALIAS[_n.lower()] = _n


def parse_priority_wcf_command(text: str) -> dict[str, Any] | None:
    """``PRIORITY wcf <op> [instance-id] [k=v…]`` or None."""
    raw = str(text or "").strip()
    m = _WCF_VERB_RE.match(raw)
    if not m:
        return None
    op_raw = (m.group(2) or "").strip()
    rest = (m.group(3) or "").strip()
    kv = {mm.group(1).lower(): mm.group(2) for mm in _KV_RE.finditer(rest)}
    tokens = [t for t in rest.split() if "=" not in t]
    instance = kv.get("instance") or kv.get("id") or (tokens[0] if tokens else "")
    return {
        "job_id": (m.group(1) or "").lower(),
        "op": _OP_ALIAS.get(op_raw.lower(), op_raw),
        "instance": instance,
        "fields": {
            k: v
            for k, v in kv.items()
            if k not in {"instance", "id"}
        },
    }


def run_priority_wcf(
    text: str,
    *,
    allowlist: Any = None,
    allowlist_path: Any = None,
    install_root: Any = None,
    cred_fetcher: Callable[[str], str] | None = None,
    passed_password: str | None = None,
    http_post: Callable[..., tuple[int, str]] | None = None,
    mode: str = "relay",
    allowlist_present: bool | None = None,
) -> dict[str, Any]:
    """Relay transport: same client, run on the airc box (LAN / SaaS HTTPS)."""
    parsed = parse_priority_wcf_command(text)
    if parsed is None:
        return {"ok": False, "error": WCF_BAD_OP, "via": "wcf"}
    parsed["fields"] = {
        k: v
        for k, v in (parsed.get("fields") or {}).items()
        if k not in {"password", "passwd", "pwd", "secret"}
    }
    if allowlist_present is False:
        return {
            "ok": False,
            "error": PRIORITY_NOT_INSTALLED,
            "action": "wcf",
            "via": "wcf",
        }
    inst_row: dict[str, Any] = {}
    if allowlist is not None:
        # Allowlist present: never take url/user from the IRC line (SSRF).
        if not parsed["instance"]:
            return {
                "ok": False,
                "error": "unknown-instance",
                "action": "wcf",
                "via": "wcf",
            }
        inst = allowlist.get(parsed["instance"])
        if inst is None:
            return {
                "ok": False,
                "error": "unknown-instance",
                "action": "wcf",
                "via": "wcf",
            }
        pub = inst.public_dict() if hasattr(inst, "public_dict") else dict(inst)
        inst_row = {
            "url": pub.get("url"),
            "user": pub.get("user"),
            "credentialTarget": pub.get("credentialTarget"),
            "wcfUrl": pub.get("wcfUrl") if isinstance(pub, dict) else None,
        }
    elif parsed["instance"] and install_root is not None:
        # Caller should pass allowlist; missing map is not-configured.
        inst_row = {}
    if allowlist is None and not inst_row.get("url") and not inst_row.get("wcfUrl"):
        # Direct-test path only: fields may carry url (never when allowlist is on).
        inst_row = {
            "url": parsed["fields"].get("url") or "",
            "user": parsed["fields"].get("user") or "",
            "credentialTarget": parsed["fields"].get("credentialtarget") or "",
            "wcfUrl": parsed["fields"].get("wcfurl") or "",
        }
        parsed["fields"] = {
            k: v
            for k, v in parsed["fields"].items()
            if k not in {"url", "user", "credentialtarget", "wcfurl"}
        }
    client = PriorityWcfClient(
        inst_row,
        mode=mode,
        cred_fetcher=cred_fetcher,
        passed_password=passed_password,
        http_post=http_post,
        allowlist_present=allowlist_present,
    )
    out = client.call(parsed["op"], fields=parsed["fields"] or None)
    out["action"] = "wcf"
    out["op"] = parsed["op"]
    return out
