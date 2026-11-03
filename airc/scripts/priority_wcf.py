"""Priority WCF SOAP client (FR #6035). Offline-tested; no WINRUN / web SDK / OData.

Endpoint: ``{serverUrl}/wcf/wcf/Service.svc`` unless ``wcfUrl`` / ``wcfPath``
overrides. SOAP 1.1 ``IWCFService``, SOAPAction
``http://tempuri.org/IWCFService/<Op>``. Every call carries a WS-Security
UsernameToken. Credentials: passed-in (TLS/DCC) then CredMan (FR #5659).
Never log, argv, IRC, or dump the password.
"""
from __future__ import annotations

import base64
import json
import os
import re
import socket
import ssl
import uuid
from pathlib import Path
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

# Wire names match priority-web-sdk (FR #6054). Legacy names are aliases.
_OP_TO_WIRE = {
    "GetVersion": "GetFileVersion",
    "GetFileVersion": "GetFileVersion",
    "GeneralCompanies": "GeneralCompaniesMob",
    "GeneralCompaniesMob": "GeneralCompaniesMob",
    "ProcStart": "ProcStartMob",
    "ProcStartMob": "ProcStartMob",
    "ProcContinue": "ProcContinueMob",
    "ProcContinueMob": "ProcContinueMob",
    "ProcEnd": "ProcEndMob",
    "ProcEndMob": "ProcEndMob",
    "ProcStartActivate": "ProcStartActivateMob",
    "ProcStartActivateMob": "ProcStartActivateMob",
    "ProcEditFieldsOK": "ProcEditFieldsOKMob",
    "ProcEditFieldsOKMob": "ProcEditFieldsOKMob",
    "ProcChooseFieldsOK": "ProcChooseFieldsOKMob",
    "ProcChooseFieldsOKMob": "ProcChooseFieldsOKMob",
    "ProcWarningOK": "ProcWarningOKMob",
    "ProcWarningOKMob": "ProcWarningOKMob",
    "ProcClientContinue": "ProcClientContinueMob",
    "ProcClientContinueMob": "ProcClientContinueMob",
    # GetRows / filter / active-row / end are JS API names. SOAP from
    # priority-web-sdk@3.0.39 index.js: FormQueryDlgExecuteMob (4619/4383),
    # FormJumpLineMob (4223), FormExitFormMob (3228), FormActivateMob (3185).
    "FormGetRows": "FormQueryDlgExecuteMob",
    "FormGetRowsMob": "FormQueryDlgExecuteMob",
    "GetRows": "FormQueryDlgExecuteMob",
    "GetRowsMob": "FormQueryDlgExecuteMob",
    "FormQueryDlgExecute": "FormQueryDlgExecuteMob",
    "FormQueryDlgExecuteMob": "FormQueryDlgExecuteMob",
    "FormStart": "FormStartMob",
    "FormStartMob": "FormStartMob",
    "FormSetSearchFilter": "FormQueryDlgExecuteMob",
    "FormSetActiveRow": "FormJumpLineMob",
    "FormSetActiveRowMob": "FormJumpLineMob",
    "FormJumpLine": "FormJumpLineMob",
    "FormJumpLineMob": "FormJumpLineMob",
    "FormActivate": "FormActivateMob",
    "FormActivateMob": "FormActivateMob",
    "FormEnd": "FormExitFormMob",
    "FormEndMob": "FormExitFormMob",
    "FormExitForm": "FormExitFormMob",
    "FormExitFormMob": "FormExitFormMob",
    "ProcKillProcess": "ProcKillProcessMob",
    "ProcKillProcessMob": "ProcKillProcessMob",
}
OPS = tuple(dict.fromkeys(_OP_TO_WIRE.values()))


def resolve_wcf_op(op: str) -> str | None:
    """Map IRC/legacy names to SDK WCF operations; None if unknown."""
    raw = str(op or "").strip()
    if raw in _OP_TO_WIRE:
        return _OP_TO_WIRE[raw]
    key = raw.lower()
    for alias, wire in _OP_TO_WIRE.items():
        if alias.lower() == key:
            return wire
    extra = {
        "version": "GetFileVersion",
        "companies": "GeneralCompaniesMob",
    }
    return extra.get(key)

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
    # FR #6056: no WS-Addressing. basicHttpBinding + web-sdk use SOAPAction HTTP only.
    _ = (endpoint, message_id)
    body_el = (
        f'<{name} xmlns="{TEMPURI}"/>'
        if not inner
        else f'<{name} xmlns="{TEMPURI}">{inner}</{name}>'
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<s:Envelope xmlns:s="{SOAP_NS}" xmlns:u="{WSU_NS}">'
        "<s:Header>"
        f"{pns}"
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
    """Apply every secret to the already-redacted text (FR #6049)."""
    s = str(text or "")
    for piece in secrets:
        if piece:
            s = redact(s, piece)
    return s


def _xml_local(tag: str) -> str:
    return str(tag or "").rsplit("}", 1)[-1]


def _find_op_result(root: ET.Element) -> tuple[str, str]:
    """Return (Result text, Result element local name) if present."""
    for el in root.iter():
        name = _xml_local(el.tag)
        if name.endswith("Result") and name != "Result":
            return ("".join(el.itertext()).strip(), name)
    return "", ""


def _maybe_b64_decode(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    try:
        pad = (-len(raw)) % 4
        data = base64.b64decode(raw + ("=" * pad), validate=False)
    except Exception:  # noqa: BLE001
        return raw
    if not data:
        return raw
    try:
        decoded = data.decode("utf-8")
    except UnicodeDecodeError:
        return raw
    # Treat as base64 only when it clearly changed and looks textual.
    if decoded == raw:
        return raw
    if all(32 <= ord(ch) <= 126 or ch in "\r\n\t" for ch in decoded[:80]):
        return decoded
    return raw


def _dnames_from(obj: Any) -> list[str]:
    names: list[str] = []
    if isinstance(obj, list):
        for item in obj:
            names.extend(_dnames_from(item))
        return names
    if isinstance(obj, dict):
        dn = obj.get("DNAME") or obj.get("dname")
        if dn:
            names.append(str(dn))
        else:
            for val in obj.values():
                names.extend(_dnames_from(val))
    return names


def decorate_mob_result(parsed: dict[str, Any], result_text: str) -> None:
    """Decode Mob <Op>Result (often base64 JSON) into compact fields."""
    decoded = _maybe_b64_decode(result_text)
    if not decoded:
        return
    parsed["body"] = decoded[:400]
    parsed["_decoded"] = decoded
    parsed["has_result"] = True
    try:
        loaded = json.loads(decoded)
    except json.JSONDecodeError:
        if decoded.count(".") >= 2 and " " not in decoded.strip():
            parsed["version"] = decoded.strip()
        return
    names = _dnames_from(loaded)
    if names:
        parsed["companies"] = names
        parsed["count"] = len(names)
        parsed.pop("body", None)


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
    result_text, result_name = _find_op_result(root)
    body = root.find(f".//{{{SOAP_NS}}}Body")
    text = ""
    if body is not None:
        text = "".join(body.itertext()).strip()
    out: dict[str, Any] = {"ok": True, "body": text[:4000], "via": "wcf"}
    if result_text:
        decorate_mob_result(out, result_text)
        if result_name:
            out["result_el"] = result_name
    return out


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
        requested = str(op or "").strip()
        name = resolve_wcf_op(requested)
        if not name:
            return {"ok": False, "error": WCF_BAD_OP, "op": requested, "via": "wcf"}
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
        # FR #6058: HR Smith returns HTTP 400 with a valid <Op>Result.
        has_result = bool(
            parsed.get("has_result")
            or parsed.get("version")
            or parsed.get("companies")
        )
        if not (200 <= int(status) <= 299):
            if has_result and parsed.get("ok") is True:
                parsed.pop("error", None)
            else:
                parsed["ok"] = False
                if not is_real_fault:
                    parsed["error"] = WCF_HTTP_ERROR
        if has_result and parsed.get("ok") is True:
            parsed.pop("raw", None)
        else:
            parsed["raw"] = raw
        want_full = str((fields or {}).get("full") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "full",
        }
        decoded = parsed.pop("_decoded", None)
        parsed.pop("has_result", None)
        parsed.pop("result_el", None)
        if decoded:
            parsed["decoded"] = decoded
        if want_full and decoded:
            parsed["result"] = str(decoded)[:800]
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
    "getversion": "GetFileVersion",
    "version": "GetFileVersion",
    "getfileversion": "GetFileVersion",
    "generalcompanies": "GeneralCompaniesMob",
    "companies": "GeneralCompaniesMob",
    "generalcompaniesmob": "GeneralCompaniesMob",
    "procstart": "ProcStartMob",
    "procstartmob": "ProcStartMob",
    "proccontinue": "ProcContinueMob",
    "proccontinuemob": "ProcContinueMob",
    "procend": "ProcEndMob",
    "procendmob": "ProcEndMob",
}
for _n in list(_OP_TO_WIRE.keys()) + list(OPS):
    _OP_ALIAS[_n.lower()] = _OP_TO_WIRE.get(_n, _n)


def parse_priority_wcf_command(text: str) -> dict[str, Any] | None:
    """``PRIORITY wcf <op> [instance-id] [k=v…]`` or ``wcf prepare form``."""
    raw = str(text or "").strip()
    m = _WCF_VERB_RE.match(raw)
    if not m:
        return None
    op_raw = (m.group(2) or "").strip()
    rest = (m.group(3) or "").strip()
    kv = {mm.group(1).lower(): mm.group(2) for mm in _KV_RE.finditer(rest)}
    tokens = [t for t in rest.split() if "=" not in t]
    if op_raw.lower() == "prepare":
        if tokens and tokens[0].lower() == "form":
            tokens = tokens[1:]
        ename = str(kv.get("ename") or kv.get("name") or "").strip().upper()
        if not ename and tokens:
            ename = tokens[0].strip().upper()
            tokens = tokens[1:]
        instance = kv.get("instance") or kv.get("id") or (tokens[0] if tokens else "")
        return {
            "job_id": (m.group(1) or "").lower(),
            "op": "prepare",
            "kind": "prepare_form",
            "ename": ename,
            "instance": instance,
            "fields": {
                k: v
                for k, v in kv.items()
                if k not in {"instance", "id", "ename", "name"}
            },
        }
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


PREPARE_STEP_MAX = 40
_PREPARE_FORM_EXEC = "FORMPREPDRCT2"
_ENAME_RE = re.compile(r"^[A-Z0-9_]{1,20}$")
_UNSCOPED_PREPARE_ENAMES = frozenset(
    {"FORMPREP", "FORMPREPDRCT2", "REPPREP", "PROCPREP"}
)
_GENERIC_START_OPS = frozenset(
    {
        "ProcStartMob",
        "ProcStartActivateMob",
        "ProcStart",
        "ProcStartActivate",
    }
)
# SOAP names prepare may emit (must exist in priority-web-sdk/index.js).
PREPARE_SDK_OPS = frozenset(
    {
        "FormStartMob",  # index.js FormStartMob SOAPAction
        "FormQueryDlgExecuteMob",  # GetRows / SetSearchFilter
        "FormJumpLineMob",  # SetActiveRow
        "FormActivateMob",  # statexml + before
        "FormExitFormMob",  # EndCurrentForm
        "ProcStartActivateMob",
        "ProcContinueMob",
        "ProcChooseFieldsOKMob",
        "ProcEditFieldsOKMob",
        "ProcWarningOKMob",
        "ProcClientContinueMob",
        "ProcKillProcessMob",
        "ProcEndMob",
    }
)


def _step_from_result(out: dict[str, Any]) -> dict[str, Any]:
    blob = out.get("decoded") or out.get("body") or out.get("result") or ""
    if isinstance(blob, dict):
        return blob
    try:
        loaded = json.loads(str(blob))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _activate_link(blob: dict[str, Any]) -> dict[str, str] | None:
    acts = blob.get("Activate")
    if isinstance(acts, list) and acts and isinstance(acts[0], dict):
        row = acts[0]
        table = str(row.get("table") or "").strip()
        link = str(row.get("link") or "").strip()
        linkid = str(row.get("linkid") or row.get("linkId") or "").strip()
        if table and link and linkid:
            return {"table": table, "link": link, "linkid": linkid}
    table = str(blob.get("table") or "").strip()
    link = str(blob.get("link") or "").strip()
    linkid = str(blob.get("linkid") or "").strip()
    if table and link and linkid:
        return {"table": table, "link": link, "linkid": linkid}
    return None


def _iter_row_dicts(blob: dict[str, Any]) -> list[dict[str, Any]]:
    rows = blob.get("rows")
    if isinstance(rows, list):
        return [r for r in rows if isinstance(r, dict)]
    pack = blob.get("RowsData")
    if isinstance(pack, dict):
        found: list[dict[str, Any]] = []
        for table in pack.values():
            if not isinstance(table, dict):
                continue
            for row in table.values():
                if isinstance(row, dict):
                    found.append(row)
        if found:
            return found
    for key in ("EFORM", "FORMPREPERRS"):
        table = blob.get(key)
        if isinstance(table, dict):
            return [r for r in table.values() if isinstance(r, dict)]
    return []


def _row_count(blob: dict[str, Any]) -> int:
    return len(_iter_row_dicts(blob))


def _row_enames(blob: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for row in _iter_row_dicts(blob):
        val = row.get("ENAME") or row.get("ename")
        if val is not None:
            names.append(str(val).strip().upper())
    return names


def _take_statexml(*sources: Any) -> str:
    for src in sources:
        if isinstance(src, dict):
            val = src.get("statexml") or src.get("StateXml") or src.get("state")
            if val:
                return str(val)
        elif isinstance(src, str) and src.strip().startswith("{"):
            try:
                loaded = json.loads(src)
            except json.JSONDecodeError:
                continue
            if isinstance(loaded, dict):
                val = loaded.get("statexml") or loaded.get("StateXml")
                if val:
                    return str(val)
    return ""


def use_prepare_verb(op: str, fields: dict[str, Any] | None) -> bool:
    """True when a generic start would fire unscoped FORMPREP (FR #6079)."""
    name = resolve_wcf_op(op) or str(op or "").strip()
    if name not in _GENERIC_START_OPS and str(op or "").strip() not in _GENERIC_START_OPS:
        return False
    ename = str((fields or {}).get("ename") or (fields or {}).get("ENAME") or "")
    return ename.strip().upper() in _UNSCOPED_PREPARE_ENAMES


def _write_prepare_log(job_id: str, payload: dict[str, Any], extras: list[str]) -> None:
    jid = (job_id or "").strip().lower()
    home = (os.environ.get("AIRC_HOME") or os.environ.get("AIRC_CONSOLE_HOME") or "").strip()
    if not jid or not home:
        return
    dest = Path(home) / "jobs" / jid / "wcf-prepare.json"
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, separators=(",", ":"))
        dest.write_text(redact_all(text, *extras), encoding="utf-8")
    except OSError:
        return


def run_wcf_form_prepare(
    client: PriorityWcfClient,
    *,
    ename: str,
    job_id: str = "",
    extras: list[str] | None = None,
) -> dict[str, Any]:
    """Scoped FORMPREP via EFORM + SDK SOAP (FR #6060 / #6073 / #6079)."""
    form = str(ename or "").strip().upper()
    secrets = [x for x in (extras or []) if x]
    pw, _cerr = client._secret()
    if pw:
        secrets.append(pw)
    key_target = str(
        client.instance.get("wcfAppKeyTarget")
        or client.instance.get("wcf_app_key_target")
        or ""
    ).strip()
    if key_target and client._fetch is not None:
        try:
            app_key = client._fetch(key_target) or ""
        except Exception:  # noqa: BLE001
            app_key = ""
        if app_key:
            secrets.append(app_key)
    if not form:
        return {
            "ok": False,
            "error": "ename_missing",
            "action": "wcf",
            "op": "prepare",
            "via": client.mode,
        }
    if not _ENAME_RE.match(form):
        return {
            "ok": False,
            "error": "ename_invalid",
            "action": "wcf",
            "op": "prepare",
            "via": client.mode,
        }
    if not str(job_id or "").strip():
        return {
            "ok": False,
            "error": "job_id_required",
            "action": "wcf",
            "op": "prepare",
            "via": client.mode,
        }
    session = ""
    steps: list[dict[str, Any]] = []
    messages: list[str] = []
    last_type = ""
    last_message = ""
    err_n = 0
    error = ""
    ended = False
    form_open = False
    log_steps: list[dict[str, Any]] = []

    def _cleanup() -> None:
        if session:
            client.call("ProcEndMob", fields={"session": session})
        else:
            client.call("ProcEndMob")
        if form_open:
            client.call(
                "FormExitFormMob",
                fields={"statexml": statexml} if statexml else None,
            )

    statexml = ""
    try:
        opened = client.call("FormStartMob", fields={"form": "EFORM"})
        if opened.get("ok") is not True:
            error = str(opened.get("error") or "form_start_failed")
            raise RuntimeError(error)
        form_open = True
        opened_step = _step_from_result(opened)
        statexml = _take_statexml(opened_step, opened, opened.get("decoded")) or statexml
        filt_xml = base64.b64encode(
            json.dumps({"ENAME": form}).encode("utf-8")
        ).decode("ascii")
        found = client.call(
            "FormQueryDlgExecuteMob",
            fields={
                "statexml": statexml,
                "add": "false",
                "xml": filt_xml,
                "top": "0",
            },
        )
        if found.get("ok") is not True:
            error = str(found.get("error") or "search_failed")
            raise RuntimeError(error)
        found_step = _step_from_result(found)
        statexml = _take_statexml(found_step, found) or statexml
        names = _row_enames(found_step)
        n_rows = _row_count(found_step)
        if n_rows != 1:
            error = "ename_not_unique"
            raise RuntimeError(error)
        if names and names[0] != form:
            error = "ename_mismatch"
            raise RuntimeError(error)
        if not names:
            error = "ename_mismatch"
            raise RuntimeError(error)
        sel = client.call(
            "FormJumpLineMob",
            fields={"statexml": statexml, "line": "1"},
        )
        if sel.get("ok") is not True:
            error = str(sel.get("error") or "set_row_failed")
            raise RuntimeError(error)
        sel_step = _step_from_result(sel)
        statexml = _take_statexml(sel_step, sel) or statexml
        act = client.call(
            "FormActivateMob",
            fields={"statexml": statexml, "before": "true"},
        )
        if act.get("ok") is not True:
            error = str(act.get("error") or "activate_failed")
            raise RuntimeError(error)
        act_step = _step_from_result(act)
        statexml = _take_statexml(act_step, act) or statexml
        link = _activate_link(act_step)
        if not link:
            error = "activate_no_link"
            raise RuntimeError(error)
        start = client.call(
            "ProcStartActivateMob",
            fields={
                "type": "P",
                "ename": _PREPARE_FORM_EXEC,
                "table": link["table"],
                "link": link["link"],
                "linkid": link["linkid"],
                "avoidmessages": "1",
            },
        )
        if start.get("ok") is not True:
            error = str(start.get("error") or "activate_failed")
            raise RuntimeError(error)
        step = _step_from_result(start)
        session = str(step.get("session") or start.get("session") or "").strip()
        n = 0
        while step and n < PREPARE_STEP_MAX:
            n += 1
            if n >= PREPARE_STEP_MAX and str(step.get("type") or "").strip() != "end":
                error = "step_limit"
                client.call(
                    "ProcKillProcessMob",
                    fields={"session": session} if session else None,
                )
                break
            typ = str(step.get("type") or "").strip()
            last_type = typ
            last_message = str(step.get("message") or "")[:80]
            log_steps.append(dict(step))
            steps.append({"type": typ, "message": last_message})
            if last_message:
                messages.append(last_message[:40])
            if typ == "end":
                ended = True
                break
            if typ == "message":
                nxt = client.call("ProcContinueMob", fields={"session": session})
            elif typ == "inputHelp":
                nxt = client.call("ProcContinueMob", fields={"session": session})
            elif typ == "inputOptions":
                opts = ((step.get("input") or {}).get("Options")) or []
                sel_f = ""
                if isinstance(opts, list) and opts:
                    chosen = next(
                        (o for o in opts if isinstance(o, dict) and o.get("selected")),
                        opts[0],
                    )
                    if isinstance(chosen, dict):
                        sel_f = str(chosen.get("field") or "")
                nxt = client.call(
                    "ProcChooseFieldsOKMob",
                    fields={"session": session, "field": sel_f},
                )
            elif typ == "inputFields":
                fields = ((step.get("input") or {}).get("EditField")) or []
                filled = []
                if isinstance(fields, list):
                    for f in fields:
                        if not isinstance(f, dict):
                            continue
                        title = str(f.get("title") or "")
                        val = (
                            form
                            if re.search(r"form|ename|exec|name", title, re.I)
                            else str(f.get("value") or "")
                        )
                        filled.append({"field": f.get("field"), "op": 0, "value": val})
                xml = base64.b64encode(
                    json.dumps({"EditFields": filled}).encode("utf-8")
                ).decode("ascii")
                nxt = client.call(
                    "ProcEditFieldsOKMob",
                    fields={"session": session, "save": "false", "xml": xml},
                )
            elif typ in {"warning", "messageWarning"}:
                nxt = client.call(
                    "ProcWarningOKMob",
                    fields={"session": session, "warnings": "1"},
                )
            elif typ in {"reportOptions", "documentOptions", "displayUrl"}:
                nxt = client.call("ProcContinueMob", fields={"session": session})
            elif typ == "client":
                nxt = client.call(
                    "ProcClientContinueMob",
                    fields={"session": session, "data": ""},
                )
            else:
                error = "unknown_step"
                client.call(
                    "ProcKillProcessMob",
                    fields={"session": session} if session else None,
                )
                break
            if nxt.get("ok") is not True:
                error = str(nxt.get("error") or "step_failed")
                break
            step = _step_from_result(nxt)
            session = str(step.get("session") or session)

        err_form = client.call("FormStartMob", fields={"form": "FORMPREPERRS"})
        if err_form.get("ok") is not True:
            error = error or "errs_unknown"
        else:
            err_state = _take_statexml(_step_from_result(err_form), err_form)
            err_xml = base64.b64encode(
                json.dumps({"ENAME": form}).encode("utf-8")
            ).decode("ascii")
            err_r = client.call(
                "FormQueryDlgExecuteMob",
                fields={
                    "statexml": err_state,
                    "add": "false",
                    "xml": err_xml,
                    "top": "0",
                },
            )
            client.call(
                "FormExitFormMob",
                fields={"statexml": err_state} if err_state else None,
            )
            if err_r.get("ok") is not True:
                error = error or "errs_unknown"
            else:
                err_n = _row_count(_step_from_result(err_r))
    except Exception:  # noqa: BLE001
        if not error:
            error = "prepare_failed"
    finally:
        _cleanup()

    ok = (not error) and ended
    out = {
        "ok": ok,
        "action": "wcf",
        "op": "prepare",
        "ename": form,
        "steps": len(steps),
        "last_type": last_type,
        "last_message": last_message,
        "errs": err_n,
        "messages": messages[:4],
        "via": client.mode,
    }
    if error:
        out["error"] = error
        if error == "errs_unknown":
            out.pop("errs", None)
            out["errs"] = None
    _write_prepare_log(
        job_id,
        {"steps": log_steps or steps, "ok": ok, "ename": form},
        secrets,
    )
    for k, v in list(out.items()):
        if isinstance(v, str):
            out[k] = redact_all(v, *secrets)
    return out


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
    if parsed.get("kind") == "prepare_form":
        extra = [str(passed_password)] if passed_password else []
        return run_wcf_form_prepare(
            client,
            ename=str(parsed.get("ename") or ""),
            job_id=str(parsed.get("job_id") or ""),
            extras=extra,
        )
    if use_prepare_verb(str(parsed.get("op") or ""), parsed.get("fields")):
        return {
            "ok": False,
            "error": "use_prepare_verb",
            "action": "wcf",
            "op": parsed.get("op"),
            "via": "wcf",
        }
    out = client.call(parsed["op"], fields=parsed["fields"] or None)
    out["action"] = "wcf"
    out["op"] = parsed["op"]
    return out
