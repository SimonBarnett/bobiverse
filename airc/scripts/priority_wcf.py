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
import tempfile
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
    "ProcNewReport": "ProcNewReportMob",
    "ProcNewReportMob": "ProcNewReportMob",
    "ProcAskPrintOK": "ProcAskPrintOKMob",
    "ProcAskPrintOKMob": "ProcAskPrintOKMob",
    "ProcCheckExecution": "ProcCheckExecutionMob",
    "ProcCheckExecutionMob": "ProcCheckExecutionMob",
    "ProcCreateSpreadsheet": "ProcCreateSpreadsheetMob",
    "ProcCreateSpreadsheetMob": "ProcCreateSpreadsheetMob",
    # JS API names. SOAP builders in priority-web-sdk@3.0.39 index.js
    # (parameter expressions, not the later call sites):
    # FormQueryDlgExecuteMob $FormQueryDlgExecuteMobAsync 3309-3317
    # FormJumpLineMob        $FormJumpLineMobAsync        3264-3272
    # FormExitFormMob        $FormExitFormMobAsync        3222-3230
    # FormActivateMob        $FormActivateMobAsync        3183-3188
    # FormStartMob           $FormStartMobAsync           3399-3407
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
_PREPARE_EXEC_TYPE = "P"
_ENAME_RE = re.compile(r"^[A-Z0-9_]{1,20}$")
# Prepare programs referenced by airc (WINRUN FORMPREP, EFORM FORMPREPDRCT2,
# report/procedure REPPREPDIRECT2, plus the shorter names those calls use).
_UNSCOPED_PREPARE_ENAMES = frozenset(
    {
        "FORMPREP",
        "FORMPREPDRCT",
        "FORMPREPDRCT2",
        "REPPREP",
        "REPPREPDIRECT2",
        "PROCPREP",
    }
)
# Generic verb: read ops, plus proc session ops. Form* mutation stays off
# this verb (prepare form is the scoped path). ProcNewReportMob is not here:
# its body is type/ename/mode/format and it starts a run of that program
# ($ProcNewReportMobAsync 3642, $ReportOptions 9677). A non-prepare ProcStart
# still runs; any ename/name of a prepare program is refused first.
_GENERIC_ALLOWED_OPS = frozenset(
    {
        "GetFileVersion",
        "GeneralCompaniesMob",
        "ProcStartMob",
        "ProcStartActivateMob",
        "ProcContinueMob",
        "ProcEndMob",
        "ProcChooseFieldsOKMob",
        "ProcEditFieldsOKMob",
        "ProcWarningOKMob",
        "ProcClientContinueMob",
        "ProcAskPrintOKMob",
        "ProcKillProcessMob",
        "ProcCheckExecutionMob",
    }
)
WCF_READONLY = "wcf_readonly"
# Parameter-builder lines in the vendored priority-web-sdk@3.0.39 index.js.
SDK_BUILDER_LINES = {
    "FormActivateMob": 3183,
    "FormExitFormMob": 3222,
    "FormJumpLineMob": 3264,
    "FormQueryDlgExecuteMob": 3309,
    "FormStartMob": 3399,
    "ProcAskPrintOKMob": 3552,
    "ProcCheckExecutionMob": 3561,
    "ProcChooseFieldsOKMob": 3570,
    "ProcClientContinueMob": 3579,
    "ProcContinueMob": 3588,
    "ProcCreateSpreadsheetMob": 3597,
    "ProcEditFieldsOKMob": 3606,
    "ProcEndMob": 3615,
    "ProcKillProcessMob": 3633,
    "ProcNewReportMob": 3642,
    "ProcStartActivateMob": 3696,
    "ProcWarningOKMob": 3732,
    "ToStringData": 8099,
    "FormQuery": 4248,
    "FixFilter": 7907,
    "ParseRows": 4990,
    "ParseActivate": 5138,
    "ParsePosition": 4962,
    "ProcStep": 9503,
}
PREPARE_SDK_OPS = frozenset(
    {
        "FormStartMob",
        "FormQueryDlgExecuteMob",
        "FormJumpLineMob",
        "FormActivateMob",
        "FormExitFormMob",
        "ProcStartActivateMob",
        "ProcContinueMob",
        "ProcChooseFieldsOKMob",
        "ProcEditFieldsOKMob",
        "ProcWarningOKMob",
        "ProcClientContinueMob",
        "ProcNewReportMob",
        "ProcAskPrintOKMob",
        "ProcCheckExecutionMob",
        "ProcCreateSpreadsheetMob",
        "ProcKillProcessMob",
        "ProcEndMob",
    }
)


def _gwt_escape(text: str) -> str:
    """GWT JSONString.escapeValue for the characters prepare puts in statexml."""
    out = []
    for ch in str(text):
        o = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\b":
            out.append("\\b")
        elif ch == "\f":
            out.append("\\f")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif o < 32:
            out.append("\\u%04X" % o)
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def _gwt_json(value: Any) -> str:
    """$toString_0 / JSONArray.toString$: object pairs joined by ', ', arrays by ','."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return _gwt_escape(value)
    if isinstance(value, list):
        return "[" + ",".join(_gwt_json(item) for item in value) + "]"
    if isinstance(value, dict):
        parts = [
            _gwt_escape(str(key)) + ":" + _gwt_json(item) for key, item in value.items()
        ]
        return "{" + ", ".join(parts) + "}"
    return _gwt_escape(str(value))


def _b64_text(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def sdk_statexml(session: str, field: Any = 0, line: Any = 0, value: str = "") -> str:
    """$ToStringData (index.js 8099) / $InitDummyFormState (4450): base64 of the memento.

    curtab and key are the zero long the memento always stores (8087, None_4 intValue 0).
    active is 1 outside query mode ($CreateMemento_0 7807).
    """
    sid = str(session or "")
    if not sid:
        return ""
    doc = _gwt_json(
        {
            "Operations": [{"session": sid}],
            "Operation": [
                {
                    "field": str(field if field is not None else 0),
                    "line": str(line if line is not None else 0),
                    "curtab": "0",
                    "value": str(value or ""),
                    "active": "1",
                    "key": "0",
                }
            ],
        }
    )
    return _b64_text(doc)


def _load_blob(out: dict[str, Any]) -> dict[str, Any]:
    blob = out.get("decoded")
    if blob is None or blob == "":
        blob = out.get("body") or out.get("result") or ""
    if isinstance(blob, dict):
        return blob
    try:
        loaded = json.loads(str(blob))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _form0(blob: dict[str, Any]) -> dict[str, Any] | None:
    forms = blob.get("Form") if isinstance(blob, dict) else None
    if isinstance(forms, list) and forms and isinstance(forms[0], dict):
        return forms[0]
    return None


def _procedure0(blob: dict[str, Any]) -> dict[str, Any] | None:
    procs = blob.get("Procedure") if isinstance(blob, dict) else None
    if isinstance(procs, list) and procs and isinstance(procs[0], dict):
        return procs[0]
    return None


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class _FormMeta:
    """Column ids and window height learned from Form[0].NewTable (ParseJO 4863)."""

    def __init__(self) -> None:
        self.by_name: dict[str, int] = {}
        self.cols: dict[int, dict[int, str]] = {}
        self.field_id: dict[int, dict[str, int]] = {}
        self.height: dict[int, int] = {}

    def absorb(self, form: dict[str, Any] | None) -> None:
        if not form:
            return
        for table in form.get("NewTable") or []:
            if not isinstance(table, dict):
                continue
            tid = _as_int(table.get("table"), -1)
            if tid < 0:
                continue
            name = str(table.get("name") or "")
            if name:
                self.by_name[name] = tid
            cols = self.cols.setdefault(tid, {})
            ids = self.field_id.setdefault(tid, {})
            height = self.height.get(tid, 0)
            for col in table.get("NewColumn") or []:
                if not isinstance(col, dict):
                    continue
                zoom = str(col.get("zoomname") or "")
                fid = _as_int(col.get("field"), -1)
                if zoom and fid > 0:
                    cols[fid] = zoom
                    ids[zoom] = fid
                height = max(height, _as_int(col.get("height"), 0))
            self.height[tid] = height

    def table_id(self, name: str, form: dict[str, Any] | None = None) -> int | None:
        if name in self.by_name:
            return self.by_name[name]
        if form:
            pos = _position(form)
            if pos and pos.get("table") is not None:
                return _as_int(pos.get("table"), 0)
        return None

    def ename_field(self, tid: int | None) -> int | None:
        if tid is None:
            return None
        fid = self.field_id.get(tid, {}).get("ENAME")
        if fid and fid > 0:
            return fid
        return None


def _position(form: dict[str, Any] | None) -> dict[str, Any] | None:
    if not form:
        return None
    pos = form.get("Position")
    if isinstance(pos, list) and pos and isinstance(pos[0], dict):
        return pos[0]
    return None


def _state_from_form(form: dict[str, Any] | None, previous: str, meta: _FormMeta, tid: int | None) -> str:
    """Build the next statexml from Form[0].Position[0].session (ParseJO 4962)."""
    pos = _position(form)
    if not pos:
        return previous
    session = str(pos.get("session") or "").strip()
    if not session:
        return previous
    field = pos.get("field")
    line = pos.get("line")
    value = ""
    if form is not None and tid is not None:
        want_line = _as_int(line, -1)
        want_field = _as_int(field, -1)
        for _line, cols in _rt_groups(form, tid):
            if _line == want_line and want_field in cols:
                value = cols[want_field]
                break
    built = sdk_statexml(session, field if field is not None else 0, line if line is not None else 0, value)
    return built or previous


def _rt_groups(form: dict[str, Any], tid: int | None) -> list[tuple[int, dict[int, str]]]:
    """Form[0].RT[].FV → (line, {field id: value}). FV is tab-separated (ParseJO 4990)."""
    grouped: dict[int, dict[int, str]] = {}
    for rt in form.get("RT") or []:
        if not isinstance(rt, dict):
            continue
        parts = str(rt.get("FV") or "").split("\t")
        if not parts or not parts[0]:
            continue
        tab = abs(_as_int(parts[0], 0))
        if tid is not None and tab != tid:
            continue
        col = abs(_as_int(parts[1], 0)) if len(parts) > 1 else 0
        line = abs(_as_int(parts[2], 0)) if len(parts) > 2 else 0
        value = parts[5] if len(parts) > 5 else ""
        grouped.setdefault(line, {})[col] = value
    return sorted(grouped.items(), key=lambda item: item[0])


def _live_rows(form: dict[str, Any] | None, tid: int | None, meta: _FormMeta) -> list[dict[str, Any]]:
    """One dict per FV line. _index is the row setActiveRow / FormJumpLineMob sends."""
    if not form or tid is None:
        return []
    pos = _position(form)
    origin = _as_int(pos.get("line"), 1) if pos else 1
    offset = origin - 1
    names = meta.cols.get(tid, {})
    rows: list[dict[str, Any]] = []
    for line, cols in _rt_groups(form, tid):
        row: dict[str, Any] = {"_line": line, "_index": line + offset}
        for fid, value in cols.items():
            name = names.get(fid)
            if name:
                row[name] = value
        rows.append(row)
    return rows


def _activate_link(blob: dict[str, Any]) -> dict[str, str] | None:
    """Form[0].Activate[0].{table,link,linkid} (ParseJO 5138)."""
    form = _form0(blob)
    if not form:
        return None
    acts = form.get("Activate")
    if not (isinstance(acts, list) and acts and isinstance(acts[0], dict)):
        return None
    row = acts[0]
    table = str(row.get("table") or "").strip()
    link = str(row.get("link") or "").strip()
    linkid = str(row.get("linkid") or row.get("linkId") or "").strip()
    if table and link and linkid:
        return {"table": table, "link": link, "linkid": linkid}
    return None


def _query_top(meta: _FormMeta, tid: int | None) -> str:
    """Parent $FormQuery top = fromRow + rowcount - 2 (4248), fromRow 1."""
    height = meta.height.get(tid or -1, 0)
    return str(1 + height - 2)


def _filter_xml(field_id: int, form_name: str) -> str:
    """FixFilter (7907) then JsonToString = JSON.stringify (2946), then b64."""
    filt = {
        "or": 0,
        "QueryValues": [
            {
                "field": field_id,
                "fromval": form_name,
                "toval": "",
                "op": "=",
                "sort": 0,
                "isdesc": 0,
            }
        ],
    }
    return _b64_text(json.dumps(filt, separators=(",", ":")))


def _form_start_fields(form_name: str, *, auto_retrieve: bool) -> dict[str, str]:
    """$FormStartMobAsync body (3399). scrwidth -1, debug/sendtitles false, empty link fields."""
    return {
        "form": form_name,
        "scrwidth": "-1",
        "link": "",
        "linkid": "",
        "zoomcolumn": "0",
        "zoomname": "",
        "debug": "false",
        "sendtitles": "false",
        "zoomvalue": "",
        "autoRetrieveFirstRows": "true" if auto_retrieve else "false",
    }


def _query_fields(statexml: str, *, xml: str | None, top: str) -> dict[str, str]:
    """$FormQueryDlgExecuteMobAsync (3309): statexml, add, xml, ic=true, queryname, top."""
    fields: dict[str, str] = {}
    if statexml:
        fields["statexml"] = statexml
    fields["add"] = "false"
    if xml:
        fields["xml"] = xml
    fields["ic"] = "true"
    fields["queryname"] = ""
    fields["top"] = top
    return fields


def _with_state(statexml: str, extra: dict[str, str] | None = None) -> dict[str, str] | None:
    fields: dict[str, str] = {}
    if statexml:
        fields["statexml"] = statexml
    if extra:
        fields.update(extra)
    return fields or None


def _session_fields(session: str, extra: dict[str, str] | None = None) -> dict[str, str] | None:
    fields: dict[str, str] = {}
    if session:
        fields["session"] = session
    if extra:
        fields.update(extra)
    return fields or None


def use_prepare_verb(_op: str, fields: dict[str, Any] | None) -> bool:
    """True when a generic op's ename or name is a prepare program (FR #6079).

    Not limited to ProcStart*. ProcNewReportMob ($ReportOptions 9677) starts a
    run of the named program, and any other op can carry the same fields.
    The body is what names the program.
    """
    bag = fields or {}
    for key in ("ename", "name"):
        val = str(bag.get(key) or bag.get(key.upper()) or "").strip().upper()
        if val in _UNSCOPED_PREPARE_ENAMES:
            return True
    return False


def generic_op_allowed(op: str) -> bool:
    """Read ops and proc-session ops. Form mutation is not a generic verb."""
    raw = str(op or "").strip()
    wire = resolve_wcf_op(raw) or raw
    return wire in _GENERIC_ALLOWED_OPS


def _prepare_log_home() -> Path:
    home = (os.environ.get("AIRC_HOME") or os.environ.get("AIRC_CONSOLE_HOME") or "").strip()
    if home:
        return Path(home)
    return Path(tempfile.gettempdir()) / "airc-wcf-prepare"


def _write_prepare_log(job_id: str, payload: dict[str, Any], extras: list[str]) -> bool:
    """Write jobs/<id>/wcf-prepare.json. False when the id is blank or the write fails."""
    jid = (job_id or "").strip().lower()
    if not jid:
        return False
    dest = _prepare_log_home() / "jobs" / jid / "wcf-prepare.json"
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, separators=(",", ":"))
        dest.write_text(redact_all(text, *extras), encoding="utf-8")
    except OSError:
        return False
    return True


def _mark_log(out: dict[str, Any], wrote: bool) -> dict[str, Any]:
    """Surface a missed job log. Keep a more specific error when one is already set."""
    if wrote:
        return out
    out["log_write_failed"] = True
    if not out.get("error"):
        out["ok"] = False
        out["error"] = "log_write_failed"
    return out


def _refused_wcf(
    parsed: dict[str, Any],
    error: str,
    *,
    secrets: list[str] | None = None,
) -> dict[str, Any]:
    """Early refusal that still leaves the job log (unknown instance, not installed)."""
    jid = str(parsed.get("job_id") or "").strip().lower() or uuid.uuid4().hex[:8]
    op = parsed.get("op")
    out: dict[str, Any] = {
        "ok": False,
        "error": error,
        "action": "wcf",
        "via": "wcf",
        "job_id": jid,
    }
    if op:
        out["op"] = op
    wrote = _write_prepare_log(
        jid,
        {
            "steps": [],
            "ok": False,
            "ename": str(parsed.get("ename") or ""),
            "op": op or "",
            "row_ename": "",
            "row_enames": [],
            "activation": None,
            "error": error,
        },
        secrets or [],
    )
    return _mark_log(out, wrote)


def wcf_job_id(parsed_job_id: str, body: dict[str, Any] | None) -> str:
    """Id the IRC DONE line shows. Prepare's log id wins when the verb minted one."""
    bag = body or {}
    for cand in (bag.get("job_id"), parsed_job_id):
        jid = str(cand or "").strip().lower()
        if jid:
            return jid
    return uuid.uuid4().hex[:8]


def _proc_message_text(proc: dict[str, Any]) -> str:
    messages = proc.get("Message") or []
    if isinstance(messages, list):
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            linked = msg.get("HyperLinkedText")
            if isinstance(linked, list) and linked and isinstance(linked[0], dict):
                text = str(linked[0].get("text") or "").strip()
                if text:
                    return text
            text = str(msg.get("message") or "").strip()
            if text:
                return text
    return str(proc.get("message") or "")


def _has_warning(proc: dict[str, Any]) -> bool:
    messages = proc.get("Message") or []
    if isinstance(messages, list):
        for msg in messages:
            if isinstance(msg, dict) and str(msg.get("messagetype") or "").lower() == "warning":
                return True
    return str(proc.get("step") or "") == "warning"


def _param_block(proc: dict[str, Any]) -> dict[str, Any]:
    params = proc.get("Parameters")
    if isinstance(params, list) and params and isinstance(params[0], dict):
        return params[0]
    return {}


def _first_format(holder: dict[str, Any]) -> int:
    formats = holder.get("Formats")
    selected = 0
    first = 0
    if isinstance(formats, list):
        for item in formats:
            if not isinstance(item, dict):
                continue
            fmt = _as_int(item.get("format"), 0)
            if first == 0 and fmt:
                first = fmt
            if item.get("selected") in (1, "1", True):
                selected = fmt
    return selected or first


def _print_format(proc: dict[str, Any]) -> int:
    ask = proc.get("AskPrint")
    if isinstance(ask, list) and ask and isinstance(ask[0], dict):
        found = _first_format(ask[0])
        if found:
            return found
    return _first_format(proc)


def _classify_proc(proc: dict[str, Any]) -> tuple[str, str]:
    """Wire Procedure[0].step ($ProcStep 9503) → callback type, action."""
    if _has_warning(proc):
        return "message", "warning_ok"
    step = str(proc.get("step") or "")
    if step == "":
        return "end", "end"
    if step == "newsaved":
        return "reportOptions", "report"
    if step == "input":
        par = _param_block(proc)
        if par.get("EditField"):
            return "inputFields", "edit"
        if par.get("ChooseField"):
            return "inputOptions", "choose"
        return "inputHelp", "continue"
    if step == "displayurl":
        return "displayUrl", "continue"
    if step == "askprint":
        return "documentOptions", "print"
    if step == "CLIENT":
        return "client", "client"
    if step == "excel":
        return "excel", "excel"
    if step == "BACKGROUND":
        return "background", "continue"
    if step == "waitprocess":
        return "wait", "continue"
    if step == "waitexecution":
        return "wait", "check"
    return "unknown", "kill"


def _edit_xml(proc: dict[str, Any], form_name: str) -> str:
    par = _param_block(proc)
    filled = []
    for field in par.get("EditField") or []:
        if not isinstance(field, dict):
            continue
        title = str(field.get("title") or "")
        val = (
            form_name
            if re.search(r"form|ename|exec|name", title, re.I)
            else str(field.get("value") or "")
        )
        filled.append({"field": _as_int(field.get("field"), 0), "op": 0, "value": val})
    return _b64_text(_gwt_json({"EditFields": filled}))


def _choose_field(proc: dict[str, Any]) -> str:
    par = _param_block(proc)
    opts = par.get("ChooseField") or []
    chosen = None
    if isinstance(opts, list) and opts:
        chosen = next(
            (o for o in opts if isinstance(o, dict) and o.get("selected") in (1, "1", True)),
            opts[0],
        )
    if isinstance(chosen, dict):
        return str(_as_int(chosen.get("field"), 0))
    return "0"


def _client_data_b64() -> str:
    """ClientContinue('') → b64(JSON.stringify("")) (9788, JsonToString 2946)."""
    return _b64_text(json.dumps(""))


def _excel_url(proc: dict[str, Any]) -> str:
    urls = proc.get("URL")
    if isinstance(urls, list) and urls and isinstance(urls[0], dict):
        return str(urls[0].get("url") or "")
    return ""


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
    if not str(job_id or "").strip():
        job_id = uuid.uuid4().hex[:8]
    session = ""
    statexml = ""
    steps: list[dict[str, Any]] = []
    messages: list[str] = []
    log_steps: list[dict[str, Any]] = []
    last_type = ""
    last_message = ""
    err_n: int | None = 0
    err_rows_out: list[dict[str, Any]] | None = None
    error = ""
    ended = False
    form_open = False
    row_ename = ""
    row_enames: list[str] = []
    activation: dict[str, str] | None = None
    meta = _FormMeta()

    def _cleanup() -> None:
        client.call("ProcEndMob", fields=_session_fields(session))
        if form_open:
            client.call("FormExitFormMob", fields=_with_state(statexml))

    def _fail(code: str) -> None:
        nonlocal error
        error = code
        raise RuntimeError(code)

    def _kill() -> None:
        client.call("ProcKillProcessMob", fields=_session_fields(session))

    if not form:
        error = "ename_missing"
    elif not _ENAME_RE.match(form):
        error = "ename_invalid"
    else:
        try:
            opened = client.call("FormStartMob", fields=_form_start_fields("EFORM", auto_retrieve=False))
            if opened.get("ok") is not True:
                _fail(str(opened.get("error") or "form_start_failed"))
            form_open = True
            opened_blob = _load_blob(opened)
            opened_form = _form0(opened_blob)
            meta.absorb(opened_form)
            eform_tid = meta.table_id("EFORM", opened_form)
            statexml = _state_from_form(opened_form, statexml, meta, eform_tid)
            field_id = meta.ename_field(eform_tid)
            if field_id is None:
                _fail("ename_column_missing")
            found = client.call(
                "FormQueryDlgExecuteMob",
                fields=_query_fields(
                    statexml,
                    xml=_filter_xml(field_id, form),
                    top=_query_top(meta, eform_tid),
                ),
            )
            if found.get("ok") is not True:
                _fail(str(found.get("error") or "search_failed"))
            found_blob = _load_blob(found)
            found_form = _form0(found_blob)
            if found_form is None:
                _fail("search_failed")
            meta.absorb(found_form)
            eform_tid = meta.table_id("EFORM", found_form) or eform_tid
            statexml = _state_from_form(found_form, statexml, meta, eform_tid)
            rows = _live_rows(found_form, eform_tid, meta)
            row_enames = [str(r.get("ENAME") or "").strip() for r in rows]
            if len(rows) != 1:
                _fail("ename_not_unique")
            row_ename = row_enames[0]
            if row_ename != form:
                _fail("ename_mismatch")
            jump_line = str(_as_int(rows[0].get("_index"), 1))
            sel = client.call(
                "FormJumpLineMob",
                fields=_with_state(statexml, {"line": jump_line}),
            )
            if sel.get("ok") is not True:
                _fail(str(sel.get("error") or "set_row_failed"))
            sel_form = _form0(_load_blob(sel))
            meta.absorb(sel_form)
            statexml = _state_from_form(sel_form, statexml, meta, eform_tid)
            act = client.call(
                "FormActivateMob",
                fields=_with_state(statexml, {"before": "true"}),
            )
            if act.get("ok") is not True:
                _fail(str(act.get("error") or "activate_failed"))
            act_blob = _load_blob(act)
            act_form = _form0(act_blob)
            statexml = _state_from_form(act_form, statexml, meta, eform_tid)
            link = _activate_link(act_blob)
            if not link:
                _fail("activate_no_link")
            activation = dict(link)
            start = client.call(
                "ProcStartActivateMob",
                fields={
                    "type": _PREPARE_EXEC_TYPE,
                    "ename": _PREPARE_FORM_EXEC,
                    "table": link["table"],
                    "link": link["link"],
                    "linkid": link["linkid"],
                    "avoidmessages": "false",
                },
            )
            if start.get("ok") is not True:
                _fail(str(start.get("error") or "activate_failed"))
            proc = _procedure0(_load_blob(start))
            if proc is None:
                error = "unknown_step"
                _kill()
                proc = None
            n = 0
            while proc is not None:
                n += 1
                session = str(proc.get("session") or session or "").strip()
                kind, action = _classify_proc(proc)
                text = _proc_message_text(proc)
                last_type = kind
                last_message = text[:80]
                log_steps.append(
                    {
                        "step": str(proc.get("step") or ""),
                        "type": kind,
                        "session": session,
                        "message": last_message,
                    }
                )
                steps.append({"type": kind, "message": last_message})
                if last_message:
                    messages.append(last_message[:40])
                if action == "end":
                    ended = True
                    break
                if n >= PREPARE_STEP_MAX:
                    error = "step_limit"
                    _kill()
                    break
                if action == "warning_ok":
                    nxt = client.call(
                        "ProcWarningOKMob",
                        fields=_session_fields(session, {"warnings": "0"}),
                    )
                elif action == "choose":
                    nxt = client.call(
                        "ProcChooseFieldsOKMob",
                        fields=_session_fields(session, {"field": _choose_field(proc)}),
                    )
                elif action == "edit":
                    nxt = client.call(
                        "ProcEditFieldsOKMob",
                        fields=_session_fields(
                            session, {"save": "false", "xml": _edit_xml(proc, form)}
                        ),
                    )
                elif action == "report":
                    nxt = client.call(
                        "ProcNewReportMob",
                        fields={
                            "type": _PREPARE_EXEC_TYPE,
                            "ename": _PREPARE_FORM_EXEC,
                            "debug": "false",
                            "mode": "H",
                            "format": str(_first_format(proc)),
                            "zoomvalue": "",
                        },
                    )
                elif action == "print":
                    nxt = client.call(
                        "ProcAskPrintOKMob",
                        fields=_session_fields(
                            session,
                            {
                                "mode": "2",
                                "format": str(_print_format(proc)),
                                "sendattach": "false",
                                "copies": "1",
                                "pdf": "true",
                                "sign": "false",
                                "quick": "false",
                            },
                        ),
                    )
                elif action == "client":
                    nxt = client.call(
                        "ProcClientContinueMob",
                        fields=_session_fields(session, {"data": _client_data_b64()}),
                    )
                elif action == "excel":
                    nxt = client.call(
                        "ProcCreateSpreadsheetMob",
                        fields={
                            "type": _PREPARE_EXEC_TYPE,
                            "ename": _PREPARE_FORM_EXEC,
                            "template": "-1",
                            "sourcedatafile": _b64_text(_excel_url(proc)),
                        },
                    )
                elif action == "check":
                    nxt = client.call("ProcCheckExecutionMob", fields=_session_fields(session))
                elif action == "continue":
                    nxt = client.call("ProcContinueMob", fields=_session_fields(session))
                else:
                    error = "unknown_step"
                    _kill()
                    break
                if nxt.get("ok") is not True:
                    error = str(nxt.get("error") or "step_failed")
                    break
                nxt_proc = _procedure0(_load_blob(nxt))
                if nxt_proc is None:
                    error = "unknown_step"
                    _kill()
                    break
                proc = nxt_proc

            err_form = client.call(
                "FormStartMob",
                fields=_form_start_fields("FORMPREPERRS", auto_retrieve=True),
            )
            if err_form.get("ok") is not True:
                if not error:
                    error = "errs_unknown"
                    err_n = None
            else:
                err_blob = _load_blob(err_form)
                err_doc = _form0(err_blob)
                meta.absorb(err_doc)
                err_tid = meta.table_id("FORMPREPERRS", err_doc)
                err_state = _state_from_form(err_doc, "", meta, err_tid)
                err_field = meta.ename_field(err_tid)
                if err_field is None:
                    client.call("FormExitFormMob", fields=_with_state(err_state))
                    if not error:
                        error = "errs_unknown"
                        err_n = None
                else:
                    err_r = client.call(
                        "FormQueryDlgExecuteMob",
                        fields=_query_fields(
                            err_state,
                            xml=_filter_xml(err_field, form),
                            top=_query_top(meta, err_tid),
                        ),
                    )
                    err_reply = _load_blob(err_r) if err_r.get("ok") is True else {}
                    err_reply_form = _form0(err_reply)
                    if err_reply_form is not None:
                        meta.absorb(err_reply_form)
                        err_tid = meta.table_id("FORMPREPERRS", err_reply_form) or err_tid
                        err_state = _state_from_form(err_reply_form, err_state, meta, err_tid)
                    client.call("FormExitFormMob", fields=_with_state(err_state))
                    if err_r.get("ok") is not True or err_reply_form is None:
                        if not error:
                            error = "errs_unknown"
                            err_n = None
                    else:
                        matched = [
                            row
                            for row in _live_rows(err_reply_form, err_tid, meta)
                            if str(row.get("ENAME") or "").strip() == form
                        ]
                        err_rows_out = [
                            {k: v for k, v in row.items() if not str(k).startswith("_")}
                            for row in matched
                        ]
                        err_n = len(err_rows_out)
                        if err_n > 0 and not error:
                            error = "prepare_errors"
        except Exception as exc:  # noqa: BLE001
            # Tests raise AssertionError for an unexpected SOAP op. Do not
            # turn that into prepare_failed or the failure disappears.
            if isinstance(exc, AssertionError):
                raise
            if not error:
                error = "prepare_failed"
        finally:
            _cleanup()

    ok = (not error) and ended
    out: dict[str, Any] = {
        "ok": ok,
        "action": "wcf",
        "op": "prepare",
        "ename": form,
        "job_id": job_id,
        "steps": len(steps),
        "last_type": last_type,
        "last_message": last_message,
        "errs": err_n,
        "messages": messages[:4],
        "via": client.mode,
    }
    if err_rows_out is not None:
        out["rows"] = [
            {
                k: redact_all(v, *secrets) if isinstance(v, str) else v
                for k, v in row.items()
            }
            for row in err_rows_out
        ]
    if error:
        out["error"] = error
        if error == "errs_unknown":
            out["errs"] = None
    wrote = _write_prepare_log(
        job_id,
        {
            "steps": log_steps or steps,
            "ok": out["ok"],
            "ename": form,
            "row_ename": row_ename,
            "row_enames": row_enames,
            "activation": activation,
            "error": error,
            "errs": err_n,
            "rows": err_rows_out or [],
        },
        secrets,
    )
    _mark_log(out, wrote)
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
    secrets = [str(passed_password)] if passed_password else []
    if allowlist_present is False:
        return _refused_wcf(parsed, PRIORITY_NOT_INSTALLED, secrets=secrets)
    inst_row: dict[str, Any] = {}
    if allowlist is not None:
        # Allowlist present: never take url/user from the IRC line (SSRF).
        if not parsed["instance"]:
            return _refused_wcf(parsed, "unknown-instance", secrets=secrets)
        inst = allowlist.get(parsed["instance"])
        if inst is None:
            return _refused_wcf(parsed, "unknown-instance", secrets=secrets)
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
        return run_wcf_form_prepare(
            client,
            ename=str(parsed.get("ename") or ""),
            job_id=str(parsed.get("job_id") or ""),
            extras=secrets,
        )
    if use_prepare_verb(str(parsed.get("op") or ""), parsed.get("fields")):
        return _refused_wcf(parsed, "use_prepare_verb", secrets=secrets)
    if not generic_op_allowed(str(parsed.get("op") or "")):
        return {
            "ok": False,
            "error": WCF_READONLY,
            "action": "wcf",
            "op": parsed.get("op"),
            "via": "wcf",
        }
    out = client.call(parsed["op"], fields=parsed["fields"] or None)
    out["action"] = "wcf"
    out["op"] = parsed["op"]
    return out
