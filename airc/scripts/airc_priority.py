"""Airc Priority Client - allowlist + PRIORITY connect/status (FR #5275 / #5284) + form walk (FR #5285).

CAST IRON: never put Priority passwords on IRC, in logs, intake, or git.
Form walk uses an in-service fixture worker (no agent .mjs).
CredMan only (``credentialTarget``). Instance URLs come from the allowlist only.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

# Live config beside the example shipped in the tree.
DEFAULT_ALLOWLIST_NAME = "priority-instances.json"
EXAMPLE_ALLOWLIST_NAME = "priority-instances.example.json"

_PRIORITY_CMD_RE = re.compile(
    r"(?is)^(?:id=([0-9a-f]{8})\s+)?PRIORITY\s+(connect|status)(?:\s+(\S+))?\s*$"
)
_PRIORITY_ANY_RE = re.compile(
    r"(?is)^(?:id=([0-9a-f]{8})\s+)?PRIORITY(?:\s+(\S+).*)?$"
)
_PRIORITY_KNOWN_SUB = frozenset(
    {"connect", "status", "prepare", "formstart", "subform", "getrows"}
)

_REQUIRED_INSTANCE_KEYS = ("id", "url", "company", "user", "credentialTarget")


class PriorityConfigError(ValueError):
    """Allowlist missing, empty, malformed, or contains secrets."""


@dataclass(frozen=True)
class PriorityInstance:
    id: str
    url: str
    company: str
    user: str
    credential_target: str
    sql_server: str | None = None
    system_db: str | None = None
    prep_dir: str | None = None

    def public_dict(self) -> dict[str, Any]:
        """Identity fields safe for IRC / logs (no credential target secrets)."""
        out: dict[str, Any] = {
            "id": self.id,
            "url": self.url,
            "company": self.company,
            "user": self.user,
            "credentialTarget": self.credential_target,
        }
        if self.sql_server:
            out["sqlServer"] = self.sql_server
        if self.system_db:
            out["systemDb"] = self.system_db
        if self.prep_dir:
            out["prepDir"] = self.prep_dir
        return out


def resolve_allowlist_path(install_root: str | Path | None = None) -> Path:
    """Prefer ``<install>/config/priority-instances.json``; else example for docs/tests."""
    roots: list[Path] = []
    if install_root:
        roots.append(Path(install_root))
    here = Path(__file__).resolve()
    # airc/scripts -> airc
    roots.append(here.parents[1])
    env = (os.environ.get("AIRC_PRIORITY_ALLOWLIST") or "").strip()
    if env:
        return Path(env)
    for root in roots:
        cfg = root / "config" / DEFAULT_ALLOWLIST_NAME
        if cfg.is_file():
            return cfg
    for root in roots:
        ex = root / "config" / EXAMPLE_ALLOWLIST_NAME
        if ex.is_file():
            return ex
    raise PriorityConfigError("priority-instances allowlist missing")


def _reject_password_keys(obj: Any, path: str = "$") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            lk = str(k).lower()
            if "pass" in lk or lk in {"secret", "token", "pwd"}:
                raise PriorityConfigError(f"password/secret key refused at {path}.{k}")
            _reject_password_keys(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _reject_password_keys(v, f"{path}[{i}]")


def load_priority_allowlist(path: str | Path | None = None) -> dict[str, PriorityInstance]:
    """Load instances keyed by id. Fail closed on empty/missing/bad schema."""
    p = Path(path) if path else resolve_allowlist_path()
    if not p.is_file():
        raise PriorityConfigError(f"allowlist missing: {p}")
    raw = p.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        text = raw.decode("utf-8-sig")
    else:
        text = raw.decode("utf-8")
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as e:
        raise PriorityConfigError(f"allowlist JSON invalid: {e}") from e
    _reject_password_keys(doc)
    if not isinstance(doc, dict):
        raise PriorityConfigError("allowlist root must be an object")
    instances = doc.get("instances")
    if not isinstance(instances, list) or not instances:
        raise PriorityConfigError("allowlist instances empty")
    out: dict[str, PriorityInstance] = {}
    for i, row in enumerate(instances):
        if not isinstance(row, dict):
            raise PriorityConfigError(f"instances[{i}] must be an object")
        for key in _REQUIRED_INSTANCE_KEYS:
            if not str(row.get(key) or "").strip():
                raise PriorityConfigError(f"instances[{i}] missing {key}")
        url = str(row["url"]).strip()
        if not url.lower().startswith("https://"):
            raise PriorityConfigError(f"instances[{i}] url must be https://")
        iid = str(row["id"]).strip()
        if iid in out:
            raise PriorityConfigError(f"duplicate instance id {iid}")
        out[iid] = PriorityInstance(
            id=iid,
            url=url,
            company=str(row["company"]).strip(),
            user=str(row["user"]).strip(),
            credential_target=str(row["credentialTarget"]).strip(),
            sql_server=(str(row["sqlServer"]).strip() if row.get("sqlServer") else None),
            system_db=(str(row["systemDb"]).strip() if row.get("systemDb") else None),
            prep_dir=(str(row["prepDir"]).strip() if row.get("prepDir") else None),
        )
    return out


def get_instance(
    instance_id: str,
    allowlist: Mapping[str, PriorityInstance] | None = None,
    *,
    path: str | Path | None = None,
) -> PriorityInstance:
    al = allowlist if allowlist is not None else load_priority_allowlist(path)
    iid = (instance_id or "").strip()
    if not iid or iid not in al:
        raise PriorityConfigError(f"unknown instance id: {iid or '?'}")
    return al[iid]


def fetch_credman_password(
    target: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> str:
    """Read a generic CredMan password for ``target``. Never log the return value.

    FR #5526: default path uses native CredReadW (``airc_credman``). A supplied
    ``runner`` keeps the legacy PowerShell path for tests/compatibility.
    """
    t = (target or "").strip()
    if not t:
        raise PriorityConfigError("credentialTarget empty")
    if runner is None:
        import airc_credman as _cred

        try:
            pair = _cred.read_generic_credential(t)
        except _cred.CredmanError as e:
            raise PriorityConfigError(f"credman-read-failed:{e.reason}") from e
        if pair is None:
            raise PriorityConfigError("credman-missing")
        if not pair.password:
            raise PriorityConfigError("credman-empty")
        return pair.password

    # Legacy PowerShell / Add-Type path (injected runner only).
    ps = os.environ.get("SystemRoot", r"C:\Windows") + r"\System32\WindowsPowerShell\v1.0\powershell.exe"
    script = r"""
param([Parameter(Mandatory=$true)][string]$Target)
$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class BobCredRead {
  [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
  public struct CREDENTIAL {
    public uint Flags; public uint Type; public string TargetName; public string Comment;
    public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
    public uint CredentialBlobSize; public IntPtr CredentialBlob; public uint Persist;
    public uint AttributeCount; public IntPtr Attributes; public string TargetAlias; public string UserName;
  }
  [DllImport("advapi32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
  public static extern bool CredRead(string target, uint type, int reserved, out IntPtr cred);
  [DllImport("advapi32.dll", SetLastError=true)]
  public static extern void CredFree(IntPtr cred);
  public static string ReadGeneric(string target) {
    IntPtr p;
    if (!CredRead(target, 1, 0, out p) || p == IntPtr.Zero) return null;
    try {
      var c = (CREDENTIAL)Marshal.PtrToStructure(p, typeof(CREDENTIAL));
      if (c.CredentialBlob == IntPtr.Zero || c.CredentialBlobSize == 0) return "";
      return Marshal.PtrToStringUni(c.CredentialBlob, (int)c.CredentialBlobSize / 2);
    } finally { CredFree(p); }
  }
}
"@
$pw = [BobCredRead]::ReadGeneric($Target)
if ($null -eq $pw) { Write-Output 'CRED_MISSING'; exit 2 }
[Console]::Out.Write($pw)
"""
    try:
        p = runner(
            [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script, "-Target", t],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as e:  # noqa: BLE001
        raise PriorityConfigError(f"credman-read-failed:{type(e).__name__}") from e
    out = p.stdout or ""
    if p.returncode != 0 or out.strip() == "CRED_MISSING":
        raise PriorityConfigError("credman-missing")
    if not out:
        raise PriorityConfigError("credman-empty")
    return out


ConnectFn = Callable[[PriorityInstance, str], dict[str, Any]]


def mock_connect(instance: PriorityInstance, password: str) -> dict[str, Any]:
    """Fixture connector for SelfTest (FR #5284). Requires non-empty password; never echoes it."""
    if not password:
        return {"ok": False, "error": "password-empty"}
    return {
        "ok": True,
        "action": "connect",
        "id": instance.id,
        "company": instance.company,
        "url": instance.url,
        "user": instance.user,
        "mode": "mock",
    }


def parse_priority_command(text: str) -> tuple[str | None, str, str | None] | None:
    """Return ``(job_id|None, subcmd, instance_id|None)`` or None if not a PRIORITY verb."""
    m = _PRIORITY_CMD_RE.match((text or "").strip())
    if not m:
        return None
    return m.group(1), m.group(2).lower(), m.group(3)


def parse_priority_usage(text: str) -> str | None:
    """FR #5533: PRIORITY with no/unknown sub-verb. Returns job id or '' (not None).

    Known sub-verbs (connect/status/prepare/form walk) return None so their parsers win.
    """
    m = _PRIORITY_ANY_RE.match((text or "").strip())
    if not m:
        return None
    sub = (m.group(2) or "").strip().lower()
    if sub in _PRIORITY_KNOWN_SUB:
        return None
    return (m.group(1) or "").lower()


PRIORITY_USAGE_SUBVERBS = "connect|status|prepare|formStart|subform|getRows"

# FR #5616: must match airc_console.IRC_SAFE_PAYLOAD (no reverse import; cycle risk).
PRIORITY_REPLY_MAX_BYTES = 350
PRIORITY_ECHO_MAX_ESCAPED_BYTES = 64


def bound_echo_token(
    token: str,
    *,
    max_escaped: int = PRIORITY_ECHO_MAX_ESCAPED_BYTES,
) -> str:
    """Shorten a user token so its json.dumps form fits max_escaped UTF-8 bytes."""
    raw = str(token or "")
    if len(json.dumps(raw, ensure_ascii=True).encode("utf-8")) <= max_escaped:
        return raw
    lo, hi = 0, len(raw)
    best = "..."
    while lo <= hi:
        mid = (lo + hi) // 2
        cand = raw[:mid] + "..."
        if len(json.dumps(cand, ensure_ascii=True).encode("utf-8")) <= max_escaped:
            best = cand
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def format_bounded_priority_out(
    job_id: str,
    payload: dict[str, Any],
    exit_code: int,
    *,
    max_bytes: int = PRIORITY_REPLY_MAX_BYTES,
) -> tuple[str, int]:
    """Return (framed out line, effective exit). Oversized -> compact reply-too-large."""
    jid = (job_id or "").strip().lower() or "00000000"
    body = dict(payload or {})
    line_json = json.dumps(body, separators=(",", ":"), sort_keys=True)
    low = line_json.lower()
    # Key-shaped only: error codes like password-refused must stay visible.
    if re.search(r'"(?:password|passwd|secret|pwd|token)"\s*:', low):
        line_json = json.dumps(
            {"ok": False, "error": "redacted-unsafe-payload"},
            separators=(",", ":"),
        )
        out = f"out id={jid} seq=1 {line_json}"
        return out, 1
    out = f"out id={jid} seq=1 {line_json}"
    nbytes = len(out.encode("utf-8"))
    if nbytes <= max_bytes:
        return out, int(exit_code)
    action = str(body.get("action") or body.get("op") or "priority")
    fallback = {
        "ok": False,
        "action": action,
        "error": "reply-too-large",
        "bytes": nbytes,
    }
    fb_json = json.dumps(fallback, separators=(",", ":"), sort_keys=True)
    return f"out id={jid} seq=1 {fb_json}", 1



def format_priority_usage(job_id: str) -> str:
    qid = (job_id or "").strip().lower() or "00000000"
    return (
        f"err id={qid} seq=1 code=usage PRIORITY {PRIORITY_USAGE_SUBVERBS}\n"
        f"DONE id={qid} exit=2"
    )


@dataclass
class PriorityVerbResult:
    ok: bool
    exit_code: int
    job_id: str
    payload: dict[str, Any]
    error: str = ""
    pending: bool = False

    def reply_lines(self) -> list[str]:
        if self.pending:
            return []
        body = dict(self.payload)
        if self.error and "error" not in body:
            body["error"] = self.error
        # FR #5616: redact first, then bound the framed out line (never slice JSON).
        out, exit_code = format_bounded_priority_out(
            self.job_id, body, self.exit_code
        )
        return [out, f"DONE id={self.job_id} exit={exit_code}"]

    def reply_text(self) -> str:
        return "\n".join(self.reply_lines())


def _connect_work(
    inst: PriorityInstance,
    jid: str,
    *,
    cred_fetcher: Callable[[str], str] | None,
    connector: ConnectFn | None,
) -> PriorityVerbResult:
    """CredMan fetch + connector. Never put secrets in the returned payload."""
    fetch = cred_fetcher or fetch_credman_password
    password = ""
    try:
        try:
            password = fetch(inst.credential_target)
        except PriorityConfigError as e:
            return PriorityVerbResult(
                False,
                1,
                jid,
                {"ok": False, "action": "connect", "id": inst.id},
                error=str(e),
            )
        conn = connector or mock_connect
        result = conn(inst, password)
    except Exception as exc:  # noqa: BLE001 --- isolate worker faults
        return PriorityVerbResult(
            False,
            1,
            jid,
            {"ok": False, "action": "connect", "id": inst.id},
            error=f"isolated-fault:{type(exc).__name__}",
        )
    finally:
        password = ""  # noqa: F841 --- drop local reference

    if not isinstance(result, dict):
        return PriorityVerbResult(
            False,
            1,
            jid,
            {"ok": False, "action": "connect", "id": inst.id},
            error="bad-connector",
        )
    # Strip any accidental secret keys from connector output.
    safe = {k: v for k, v in result.items() if "pass" not in str(k).lower()}
    ok = bool(safe.get("ok"))
    if "action" not in safe:
        safe["action"] = "connect"
    for k, v in inst.public_dict().items():
        safe.setdefault(k, v)
    return PriorityVerbResult(ok, 0 if ok else 1, jid, safe)


def run_priority_verb(
    subcmd: str,
    instance_id: str | None,
    *,
    job_id: str | None = None,
    install_root: str | Path | None = None,
    allowlist_path: str | Path | None = None,
    allowlist: Mapping[str, PriorityInstance] | None = None,
    cred_fetcher: Callable[[str], str] | None = None,
    connector: ConnectFn | None = None,
    wait: bool = True,
    on_done: Callable[[PriorityVerbResult], Any] | None = None,
) -> PriorityVerbResult:
    """Execute ``connect`` / ``status``. Passwords never enter the returned payload.

    FR #5526: when ``wait=False`` and ``on_done`` is set for ``connect``, CredMan
    + connector run on a daemon worker thread so the IRC receive loop stays free.
    Allowlist / status / validation stay synchronous. Default ``wait=True`` keeps
    direct-call and mock behaviour unchanged.
    """
    import uuid

    jid = (job_id or uuid.uuid4().hex[:8]).lower()
    try:
        if allowlist is not None:
            al = allowlist
        elif allowlist_path is not None:
            al = load_priority_allowlist(allowlist_path)
        else:
            al = load_priority_allowlist(resolve_allowlist_path(install_root))
    except PriorityConfigError as e:
        return PriorityVerbResult(
            False, 1, jid, {"ok": False, "action": subcmd}, error=str(e)
        )

    if subcmd == "status" and not instance_id:
        ids = sorted(al.keys())
        return PriorityVerbResult(
            True,
            0,
            jid,
            {"ok": True, "action": "status", "instances": ids, "count": len(ids)},
        )

    if not instance_id:
        return PriorityVerbResult(
            False,
            2,
            jid,
            {"ok": False, "action": subcmd},
            error="instance-id-required",
        )

    try:
        inst = get_instance(instance_id, al)
    except PriorityConfigError as e:
        # FR #5616: shorten echoed id so unknown-instance reason survives IRC budget.
        bounded = bound_echo_token(instance_id or "")
        err = str(e)
        if "unknown instance" in err.lower():
            err = f"unknown instance id: {bounded or '?'}"
        return PriorityVerbResult(
            False, 1, jid, {"ok": False, "action": subcmd, "id": bounded}, error=err
        )

    if subcmd == "status":
        return PriorityVerbResult(
            True,
            0,
            jid,
            {"ok": True, "action": "status", **inst.public_dict()},
        )

    if subcmd != "connect":
        return PriorityVerbResult(
            False, 2, jid, {"ok": False}, error=f"unknown-subcmd:{subcmd}"
        )

    # FR #5526: opt-in async connect (CredMan + connector off the IRC loop).
    if not wait and on_done is not None:
        done_once = threading.Lock()
        finished = False

        def _worker() -> None:
            nonlocal finished
            res = _connect_work(
                inst, jid, cred_fetcher=cred_fetcher, connector=connector
            )
            with done_once:
                if finished:
                    return
                finished = True
            try:
                on_done(res)
            except Exception:
                pass

        threading.Thread(
            target=_worker, name="airc-priority-worker", daemon=True
        ).start()
        return PriorityVerbResult(
            True, 0, jid, {"ok": True, "action": "connect", "id": inst.id}, pending=True
        )

    return _connect_work(inst, jid, cred_fetcher=cred_fetcher, connector=connector)

# --- FR #5285 form walk (fixture read path) ---

WALK_OPS = frozenset({"formstart", "subform", "getrows"})
OP_WIRE = {"formstart": "formStart", "subform": "subform", "getrows": "getRows"}
_ID_PREFIX_RE = re.compile(r"(?is)^id=([0-9a-f]{8})\s+(.*)$")
_KV_RE = re.compile(r"(\w+)=([^\s]+)")
_WALK_VERB_RE = re.compile(
    r"(?is)^PRIORITY\s+(formStart|subform|getRows)(?:\s+(.*))?$",
)
_SECRET_KEYS = frozenset({"password", "passwd", "secret", "token", "pwd"})


@dataclass(frozen=True)
class PriorityWalkResult:
    ok: bool
    exit_code: int
    job_id: str
    lines: tuple[str, ...]
    payload: dict[str, Any]


def parse_priority_walk_command(text: str) -> tuple[str, dict[str, str]] | None:
    raw = (text or "").strip()
    leading_id = ""
    m_id = _ID_PREFIX_RE.match(raw)
    if m_id:
        leading_id = (m_id.group(1) or "").lower()
        raw = (m_id.group(2) or "").strip()
    m = _WALK_VERB_RE.match(raw)
    if not m:
        return None
    op = m.group(1)
    rest = (m.group(2) or "").strip()
    kv = {mm.group(1).lower(): mm.group(2) for mm in _KV_RE.finditer(rest)}
    # FR #5803: accept positional ``PRIORITY formStart <instance> <form>``
    # (same bare instance id as ``PRIORITY status <id>``), not only key=value.
    positionals: list[str] = []
    for tok in rest.split():
        if re.match(r"^\w+=", tok):
            continue
        positionals.append(tok)
    if "instance" not in kv and positionals:
        kv["instance"] = positionals[0]
    if "form" not in kv and len(positionals) > 1:
        kv["form"] = positionals[1]
    if "path" not in kv and len(positionals) > 2:
        kv["path"] = positionals[2]
    if leading_id and "id" not in kv:
        kv["id"] = leading_id
    return op, kv


def _priority_install_roots(install_root: str | Path | None = None) -> list[Path]:
    """FR #5523: frozen onefile __file__ is _MEIPASS; pack lives under <ai>\\airc\\airc\\."""
    roots: list[Path] = []
    if install_root:
        roots.append(Path(install_root))
    env = (os.environ.get("AIRC_INSTALL_ROOT") or "").strip()
    if env:
        roots.append(Path(env))
    frozen = bool(getattr(sys, "frozen", False)) or hasattr(sys, "_MEIPASS")
    if frozen:
        exe = Path(str(getattr(sys, "executable", "") or "")).resolve()
        if exe.parent.name.lower() == "airc":
            roots.append(exe.parent)
            roots.append(exe.parent.parent)
        elif str(exe):
            roots.append(exe.parent)
    here = Path(__file__).resolve()
    if here.parent.name.lower() == "scripts":
        roots.append(here.parents[1])
        if len(here.parents) > 2:
            roots.append(here.parents[2])
    roots.append(Path(r"C:\ai\airc"))
    out: list[Path] = []
    seen: set[str] = set()
    for r in roots:
        key = str(r).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def resolve_priority_worker_dir(install_root: str | Path | None = None) -> Path | None:
    """First existing priority-worker dir (nested pack or flat)."""
    for root in _priority_install_roots(install_root):
        for rel in (Path("airc") / "priority-worker", Path("priority-worker")):
            d = root / rel
            if (d / "priority_worker.py").is_file() or (
                d / "fixtures" / "form_walk.json"
            ).is_file():
                return d
    return None


def default_fixture_path() -> Path:
    """FR #5523: never rely on Path(__file__).parents[1] alone (frozen _MEIPASS)."""
    d = resolve_priority_worker_dir()
    if d is not None:
        return d / "fixtures" / "form_walk.json"
    return Path(__file__).resolve().parents[1] / "priority-worker" / "fixtures" / "form_walk.json"


def load_allowlist_rows(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    inst = data.get("instances")
    if not isinstance(inst, list):
        return []
    return [x for x in inst if isinstance(x, dict) and str(x.get("id") or "").strip()]


def resolve_instance_row(allowlist: list[dict[str, Any]], instance_id: str) -> dict[str, Any] | None:
    want = (instance_id or "").strip().lower()
    for row in allowlist:
        if str(row.get("id") or "").strip().lower() == want:
            return row
    return None


def _secret_in_kv(kv: dict[str, str]) -> bool:
    return any(k.lower() in _SECRET_KEYS for k in kv)


def load_fixture(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("fixture root must be an object")
    forms = data.get("forms")
    if not isinstance(forms, dict):
        raise ValueError("fixture missing forms")
    return forms


def walk_fixture(op: str, forms: dict[str, Any], kv: dict[str, str]) -> dict[str, Any]:
    form = (kv.get("form") or "").strip()
    if form not in forms:
        return {
            "ok": False,
            "error": "form-not-found",
            "form": bound_echo_token(form),
        }
    rec = forms[form]
    if not isinstance(rec, dict):
        raise ValueError("fixture form must be an object")
    wire = OP_WIRE[op.lower()]
    out: dict[str, Any] = {"ok": True, "op": wire, "form": form, "instance": kv.get("instance", "")}
    if wire == "subform":
        path = (kv.get("path") or "").strip()
        subs = rec.get("subforms") or {}
        if not isinstance(subs, dict):
            raise ValueError("fixture subforms must be an object")
        if path not in subs:
            return {
                "ok": False,
                "error": "subform-not-found",
                "form": bound_echo_token(form),
                "path": bound_echo_token(path),
            }
        out["path"] = path
        out["subform"] = subs[path]
    elif wire == "getRows":
        rows = rec.get("rows") or []
        out["rows"] = list(rows)
        out["count"] = len(rows)
    else:
        out["title"] = rec.get("title") or form
        out["subforms"] = list((rec.get("subforms") or {}).keys())
    return out


def resolve_walk_allowlist_path(install_root: str | None, override: str | None) -> Path | None:
    """FR #5535: same live-then-example resolution as PRIORITY status/connect."""
    if override:
        return Path(override)
    try:
        return resolve_allowlist_path(install_root)
    except PriorityConfigError:
        return None


def run_priority_walk(
    *,
    text: str,
    allowlist_path: Path | None,
    fixture_path: Path | None = None,
    job_id_fallback: str = "",
) -> PriorityWalkResult:
    parsed = parse_priority_walk_command(text)
    if parsed is None:
        jid = job_id_fallback or "-"
        return PriorityWalkResult(
            False,
            2,
            jid,
            (f"err id={jid} code=bad_frame msg=not-priority", f"DONE id={jid} exit=2"),
            {},
        )
    op, kv = parsed
    jid = (kv.get("id") or job_id_fallback or "00000000").lower()
    if _secret_in_kv(kv):
        payload = {"ok": False, "error": "password-refused", "action": "walk"}
        out, exit_code = format_bounded_priority_out(jid, payload, 2)
        lines = (out, f"DONE id={jid} exit={exit_code}")
        return PriorityWalkResult(False, exit_code, jid, lines, payload)
    inst_id = (kv.get("instance") or "").strip()
    allow = load_allowlist_rows(allowlist_path)
    if resolve_instance_row(allow, inst_id) is None:
        payload = {"ok": False, "error": "unknown-instance", "action": "walk"}
        out, exit_code = format_bounded_priority_out(jid, payload, 2)
        lines = (out, f"DONE id={jid} exit={exit_code}")
        return PriorityWalkResult(False, exit_code, jid, lines, payload)
    form = (kv.get("form") or "").strip()
    if not form:
        payload = {"ok": False, "error": "missing-form", "action": "walk"}
        out, exit_code = format_bounded_priority_out(jid, payload, 2)
        lines = (out, f"DONE id={jid} exit={exit_code}")
        return PriorityWalkResult(False, exit_code, jid, lines, payload)
    fix = Path(fixture_path) if fixture_path else default_fixture_path()
    failure: BaseException | str = ""
    try:
        forms = load_fixture(fix)
        payload = walk_fixture(op, forms, kv)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        failure = exc
        payload = {
            "ok": False,
            "error": "fixture-miss",
            "action": "walk",
        }
    if "action" not in payload:
        payload = {**payload, "action": "walk"}
    if not payload.get("ok"):
        try:
            import airc_fail_intake as _fail

            _fail.report_verb_failure(
                "priority",
                failure or payload["error"],
                args={
                    "op": op,
                    "instance": inst_id,
                    "form": form,
                    "path": kv.get("path", ""),
                },
                wait_s=1.0,
            )
        except Exception:
            pass
    out, exit_code = format_bounded_priority_out(
        jid, payload, 0 if payload.get("ok") else 2
    )
    lines = (out, f"DONE id={jid} exit={exit_code}")
    ok = exit_code == 0 and bool(payload.get("ok"))
    return PriorityWalkResult(ok, exit_code, jid, lines, payload)
