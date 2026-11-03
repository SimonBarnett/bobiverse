"""Priority WCF SOAP client (FR #6035). Offline-tested; no WINRUN / web SDK / OData.

Endpoint: ``{serverUrl}/wcf/wcf/Service.svc`` unless ``wcfUrl`` / ``wcfPath``
overrides. SOAP 1.1 ``IWCFService``, SOAPAction
``http://tempuri.org/IWCFService/<Op>``. Every call carries a WS-Security
UsernameToken. Credentials: passed-in (TLS/DCC) then CredMan (FR #5659).
Never log, argv, IRC, or dump the password.
"""
from __future__ import annotations

import re
import socket
import ssl
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
WSSE_NS = (
    "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
)
WSU_NS = (
    "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
)
PASSWORD_TEXT_TYPE = (
    "http://docs.oasis-open.org/wss/2004/01/"
    "oasis-200401-wss-username-token-profile-1.0#PasswordText"
)
TEMPURI = "http://tempuri.org/"
WSA_NS = "http://www.w3.org/2005/08/addressing"
SOAP_ACTION_TMPL = "http://tempuri.org/IWCFService/{op}"
WCF_HTTP_ERROR = "wcf_http_error"
RAW_BODY_MAX = 800
DEFAULT_WCF_PATH = "/wcf/wcf/Service.svc"
TIMESTAMP_TTL_S = 300
DEFAULT_TABULA_INI = "tabula.ini"
PRIORITY_NS = "PriorityNS"
_IRC_OVERRIDE_KEYS = frozenset(
    {
        "url",
        "user",
        "company",
        "tabulaini",
        "tabula_ini",
        "language",
        "authaudience",
        "auth_audience",
        "hostname",
        "appid",
        "appkey",
        "wcfappid",
        "credentialtarget",
        "wcfurl",
    }
)

OPS = ("GetVersion", "GeneralCompanies", "ProcStart", "ProcContinue", "ProcEnd")

PRIORITY_NOT_INSTALLED = "priority_not_installed"
PRIORITY_NOT_CONFIGURED = "priority_not_configured"
WCF_AUTH_FAILED = "wcf_auth_failed"
SOAP_FAULT = "soap_fault"
WCF_SECURITY_REJECTED = "wcf_security_rejected"
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


def format_wcf_username(
    user: str,
    tabulaini: str | None = None,
    auth_audience: str | None = None,
) -> str:
    """Priority validator username: ``user\\ttabulaini[\\tauthAudience]``."""
    name = str(user or "").strip()
    ini = str(tabulaini or "").strip() or DEFAULT_TABULA_INI
    aud = str(auth_audience or "").strip()
    if aud:
        return f"{name}\t{ini}\t{aud}"
    return f"{name}\t{ini}"


def other_info_blob(*, app_id: str = "", app_key: str = "") -> str:
    parts = ["app_airc,"]
    aid = str(app_id or "").strip()
    akey = str(app_key or "").strip()
    if aid:
        parts.append(f"appid_{aid},")
    if akey:
        parts.append(f"appkey_{akey},")
    return "".join(parts)


def _wsu_time(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def build_envelope(
    op: str,
    *,
    user: str,
    password: str,
    body_fields: dict[str, Any] | None = None,
    now: datetime | None = None,
    ttl_s: int = TIMESTAMP_TTL_S,
    token_id: str | None = None,
    hostname: str | None = None,
    company: str | None = None,
    utc_offset: str | None = None,
    language: int = 3,
    other_info: str | None = None,
    emit_priority_ns: bool | None = None,
    endpoint: str | None = None,
    message_id: str | None = None,
) -> str:
    """SOAP 1.1 envelope with PriorityNS + UsernameToken + wsu:Timestamp.

    Caller must not log the result (password / appkey may be in the header).
    """
    name = str(op or "").strip()
    fields = body_fields or {}
    inner = "".join(
        f"<{k}>{_xml_escape(v)}</{k}>" for k, v in fields.items() if v is not None
    )
    created = now if now is not None else datetime.now(timezone.utc)
    expires = created + timedelta(seconds=int(ttl_s or TIMESTAMP_TTL_S))
    tid = str(token_id or f"uuid-{uuid.uuid4()}-1")
    ns = emit_priority_ns
    if ns is None:
        ns = bool(hostname or company or other_info)
    pns = ""
    if ns:
        host = _xml_escape(hostname or "")
        env = _xml_escape(company or "")
        off = _xml_escape(utc_offset if utc_offset is not None else "0")
        info = _xml_escape(other_info if other_info is not None else "app_airc,")
        lang = int(language if language is not None else 3)
        pns = (
            f'<Language xmlns="{PRIORITY_NS}">{lang}</Language>'
            f'<Hostname xmlns="{PRIORITY_NS}">{host}</Hostname>'
            f'<WinUser xmlns="{PRIORITY_NS}"></WinUser>'
            f'<UtcOffset xmlns="{PRIORITY_NS}">{off}</UtcOffset>'
            f'<Environment xmlns="{PRIORITY_NS}">{env}</Environment>'
            f'<SilverLight xmlns="{PRIORITY_NS}">2</SilverLight>'
            f'<OtherInfo xmlns="{PRIORITY_NS}">{info}</OtherInfo>'
        )
    wsa = ""
    dest = str(endpoint or "").strip()
    if dest:
        mid = str(message_id or f"urn:uuid:{uuid.uuid4()}")
        act = SOAP_ACTION_TMPL.format(op=name)
        wsa = (
            f'<a:Action s:mustUnderstand="1" xmlns:a="{WSA_NS}">{_xml_escape(act)}</a:Action>'
            f'<a:To s:mustUnderstand="1" xmlns:a="{WSA_NS}">{_xml_escape(dest)}</a:To>'
            f'<a:MessageID xmlns:a="{WSA_NS}">{_xml_escape(mid)}</a:MessageID>'
            f'<a:ReplyTo xmlns:a="{WSA_NS}">'
            f'<a:Address>http://www.w3.org/2005/08/addressing/anonymous</a:Address>'
            "</a:ReplyTo>"
        )
    body_el = (
        f'<{name} xmlns="{TEMPURI}"/>'
        if not inner
        else f'<{name} xmlns="{TEMPURI}">{inner}</{name}>'
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<s:Envelope xmlns:s="{SOAP_NS}" xmlns:u="{WSU_NS}">'
        "<s:Header>"
        f"{pns}{wsa}"
        f'<o:Security s:mustUnderstand="1" xmlns:o="{WSSE_NS}">'
        '<u:Timestamp u:Id="_0">'
        f"<u:Created>{_wsu_time(created)}</u:Created>"
        f"<u:Expires>{_wsu_time(expires)}</u:Expires>"
        "</u:Timestamp>"
        f'<o:UsernameToken u:Id="{_xml_escape(tid)}">'
        f"<o:Username>{_xml_escape(user)}</o:Username>"
        f'<o:Password Type="{PASSWORD_TEXT_TYPE}">'
        f"{_xml_escape(password)}</o:Password>"
        "</o:UsernameToken>"
        "</o:Security>"
        "</s:Header>"
        "<s:Body>"
        f"{body_el}"
        "</s:Body>"
        "</s:Envelope>"
    )


def soap_action(op: str) -> str:
    return SOAP_ACTION_TMPL.format(op=str(op).strip())


def redact(text: str, secret: str = "", extra: str = "") -> str:
    s = str(text or "")
    if secret:
        s = s.replace(secret, "***")
    if extra:
        s = s.replace(str(extra), "***")
    return _PASS_RE.sub(r"\1=***", s)


def redact_all(text: str, *secrets: str) -> str:
    s = str(text or "")
    for piece in secrets:
        if piece:
            s = redact(s, piece)
    return s


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
        blob = f"{code} {msg}"
        err = (
            WCF_SECURITY_REJECTED
            if "invalidsecurity" in blob.lower()
            else SOAP_FAULT
        )
        return {
            "ok": False,
            "error": err,
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
        app_key = ""
        key_target = str(
            self.instance.get("wcfAppKeyTarget")
            or self.instance.get("wcf_app_key_target")
            or ""
        ).strip()
        if key_target and self._fetch is not None:
            try:
                app_key = self._fetch(key_target) or ""
            except Exception:  # noqa: BLE001
                app_key = ""
        token_user = format_wcf_username(
            user,
            tabulaini=str(
                self.instance.get("tabulaIni")
                or self.instance.get("tabula_ini")
                or DEFAULT_TABULA_INI
            ),
            auth_audience=str(
                self.instance.get("authAudience")
                or self.instance.get("auth_audience")
                or ""
            ),
        )
        host = str(self.instance.get("hostname") or "").strip() or socket.gethostname()
        company = str(self.instance.get("company") or "").strip()
        lang_raw = self.instance.get("language")
        try:
            lang = int(lang_raw) if lang_raw not in (None, "") else 3
        except (TypeError, ValueError):
            lang = 3
        info = other_info_blob(
            app_id=str(self.instance.get("wcfAppId") or self.instance.get("wcf_app_id") or ""),
            app_key=app_key,
        )
        envelope = build_envelope(
            name,
            user=token_user,
            password=secret,
            body_fields=fields,
            hostname=host,
            company=company,
            language=lang,
            other_info=info,
            endpoint=url,
        )
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
        extras = [x for x in (to_redact, app_key) if x]
        raw = redact_all((body or "")[:RAW_BODY_MAX], *extras)
        if status in (401, 403):
            return {
                "ok": False,
                "error": WCF_AUTH_FAILED,
                "via": self.mode,
                "http_status": status,
                "raw": raw,
            }
        parsed = parse_soap_response(body)
        is_real_fault = parsed.get("error") in (
            SOAP_FAULT,
            WCF_SECURITY_REJECTED,
        ) and parsed.get("detail") != "bad_xml"
        parsed["op"] = name
        parsed["via"] = self.mode
        parsed["endpoint_ok"] = True
        parsed["http_status"] = status
        parsed["raw"] = raw
        if not (200 <= int(status) <= 299):
            parsed["ok"] = False
            if not is_real_fault:
                parsed["error"] = WCF_HTTP_ERROR
        if extras:
            for k, v in list(parsed.items()):
                if isinstance(v, str):
                    parsed[k] = redact_all(v, *extras)
        app_key = ""
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
            "company": pub.get("company"),
            "tabulaIni": pub.get("tabulaIni") or DEFAULT_TABULA_INI,
            "authAudience": pub.get("authAudience"),
            "language": pub.get("language"),
            "hostname": pub.get("hostname"),
            "credentialTarget": pub.get("credentialTarget"),
            "wcfUrl": pub.get("wcfUrl") if isinstance(pub, dict) else None,
            "wcfAppId": pub.get("wcfAppId"),
            "wcfAppKeyTarget": pub.get("wcfAppKeyTarget"),
        }
    elif parsed["instance"] and install_root is not None:
        # Caller should pass allowlist; missing map is not-configured.
        inst_row = {}
    if allowlist is None and not inst_row.get("url") and not inst_row.get("wcfUrl"):
        # Direct-test path only: fields may carry url (never when allowlist is on).
        inst_row = {
            "url": parsed["fields"].get("url") or "",
            "user": parsed["fields"].get("user") or "",
            "company": parsed["fields"].get("company") or "",
            "tabulaIni": parsed["fields"].get("tabulaini") or DEFAULT_TABULA_INI,
            "credentialTarget": parsed["fields"].get("credentialtarget") or "",
            "wcfUrl": parsed["fields"].get("wcfurl") or "",
        }
        parsed["fields"] = {
            k: v
            for k, v in parsed["fields"].items()
            if k not in _IRC_OVERRIDE_KEYS
        }
    parsed["fields"] = {
        k: v for k, v in parsed["fields"].items() if k not in _IRC_OVERRIDE_KEYS
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
