"""Airc LEGION verb + isolated worker (FR #5308 / #5309 / FR #5594).

FR-A: verb + stub. FR-B: import ``airc_network_installer`` for one host,
profile client, latest Release MSI, no --force. Auth matches UPDATE.
FR #5594: SYSTEM / computer account is the last resort.
FR #5659: identity order passed (DCC CRED) -> CredMan PriorityAirc/LegionAdmin
-> SYSTEM. Wrong passed/CredMan auth fails closed (no silent fallback).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from socket import gethostname as socket_hostname
from typing import Any, Callable

# In-service module (FR #3991). LEGION must not shell a peer installer exe.
import airc_network_installer as _netinst  # noqa: F401

LEGION_TIMEOUT_S = 900

_LEGION_CMD_RE = re.compile(
    r"(?is)^(?:id=([0-9a-f]{8})\s+)?LEGION(?:\s+(?P<rest>.*))?$"
)
_HOST_RE = re.compile(r"(?i)^[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?(?:\.[a-z0-9\-]{1,63})*$")
_IPV4_RE = re.compile(
    r"^(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}$"
)


@dataclass
class LegionVerbResult:
    ok: bool
    reply: str
    job_id: str = ""
    status: str = ""
    error: str = ""
    failures: list[dict[str, Any]] = field(default_factory=list)
    # FR #5530 retest: WhatIf plan fields for the DCC log (msi/psexec).
    msi: str = ""
    psexec: str = ""
    plan: dict[str, Any] = field(default_factory=dict)
    identity: str = ""
    computer_account: str = ""
    identity_label: str = ""

    def reply_text(self) -> str:
        return self.reply


def _classify_target(raw: str) -> str | None:
    t = (raw or "").strip()
    if not t:
        return "empty"
    if "," in t or ";" in t:
        low = t.lower()
        if low.startswith("ou=") or "ou=" in low or low.startswith("cn="):
            return "ou"
        return "list"
    if t.lower().startswith("ou=") or t.lower().startswith("cn="):
        return "ou"
    if _IPV4_RE.match(t) or _HOST_RE.match(t):
        return None
    # FR #5528: punctuation/illegal hostname is not a host list.
    return "invalid"


def parse_legion_command(text: str) -> dict[str, Any] | None:
    m = _LEGION_CMD_RE.match((text or "").strip())
    if not m:
        return None
    # FR #5659: reject plaintext password= on IRC (use DCC CRED).
    import airc_identity as _ident
    import airc_passed_cred as _pcred

    if _ident.irc_line_has_plaintext_secret(text or ""):
        return {
            "qid": (m.group(1) or "").lower(),
            "error": "secrets-on-irc",
            "target": "",
            "whatif": False,
        }
    rest = (m.group("rest") or "").strip()
    whatif = bool(re.search(r"(?i)(?:^|\s)-WhatIf(?:\s|$)", rest))
    rest = re.sub(r"(?i)(?:^|\s)-WhatIf(?:\s|$)", " ", rest).strip()
    cred_id, rest = _pcred.extract_cred_ref(rest)
    parts = [p for p in rest.split() if p]
    qid = (m.group(1) or "").lower()
    flags = [p for p in parts if p.startswith("-")]
    hosts = [p for p in parts if not p.startswith("-")]
    if flags:
        return {
            "qid": qid,
            "error": "unknown-flag",
            "unknown_flag": flags[0],
            "target": " ".join(hosts),
            "whatif": whatif,
            "cred_id": cred_id,
        }
    if not hosts:
        return {
            "qid": qid,
            "error": "empty",
            "target": "",
            "whatif": whatif,
            "cred_id": cred_id,
        }
    if len(hosts) > 1:
        return {
            "qid": qid,
            "error": "list",
            "target": " ".join(hosts),
            "whatif": whatif,
            "cred_id": cred_id,
        }
    err = _classify_target(hosts[0])
    if err:
        return {
            "qid": qid,
            "error": err,
            "target": hosts[0],
            "whatif": whatif,
            "cred_id": cred_id,
        }
    return {
        "qid": qid,
        "error": None,
        "target": hosts[0],
        "whatif": whatif,
        "cred_id": cred_id,
    }

_ALLOWED_MSI_PREFIX = "https://github.com/SimonBarnett/bobiverse/releases"
CREDMAN_TARGET = "PriorityAirc/LegionAdmin"
_CREDMAN_TARGET = CREDMAN_TARGET
_USE_CREDMAN_ENV = "AIRC_LEGION_USE_CREDMAN"
_ACCESS_DENIED_RE = re.compile(
    r"(?is)access(?: is)? denied|winerror[\s:=]?5\b|error[\s:=]?5\b|"
    r"1326|logon failure|admin\$|winrm"
)


class LegionCredmanError(RuntimeError):
    """CredMan target missing or unreadable (fail closed)."""


def legion_system_identity(
    *,
    hostname_fn: Callable[[], str] | None = None,
    domain_fn: Callable[[], str] | None = None,
) -> dict[str, str]:
    """FR #5594: LocalSystem as DOMAIN\\HOST$ (or HOST$ on workgroup)."""
    host = str((hostname_fn or socket_hostname)() or "LOCAL").split(".")[0]
    host = re.sub(r"[^A-Za-z0-9\-]", "", host).upper() or "LOCAL"
    domain = str((domain_fn or (lambda: os.environ.get("USERDOMAIN") or ""))() or "")
    domain = re.sub(r"[^A-Za-z0-9\-]", "", domain).upper()
    if domain and domain not in ("WORKGROUP", host):
        acct = f"{domain}\\{host}$"
    else:
        acct = f"{host}$"
    return {
        "identity": "SYSTEM",
        "computer_account": acct,
        "identity_label": f"SYSTEM ({acct})",
    }


def _credman_fallback_requested() -> bool:
    raw = str(os.environ.get(_USE_CREDMAN_ENV) or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _access_denied_reason(blob: str) -> bool:
    return bool(_ACCESS_DENIED_RE.search(blob or ""))


def _system_access_hint(account: str) -> str:
    return (
        f"source computer account {account} must be in the target local "
        "Administrators group (GPO restricted groups or Bob Fleet installers AD group)"
    )


def stub_legion_work(
    target: str,
    *,
    whatif: bool = False,
) -> dict[str, Any]:
    return {
        "ok": True,
        "target": target,
        "whatif": bool(whatif),
        "invoked_installer": False,
        "force": False,
        "timeout_s": LEGION_TIMEOUT_S,
        "profile": "client",
    }


def _msi_allowed(msi: str | None) -> bool:
    raw = (msi or "").strip()
    if not raw:
        return True
    if "://" not in raw:
        return True
    return raw.lower().startswith(_ALLOWED_MSI_PREFIX.lower())


def read_legion_credman(
    *,
    target: str = CREDMAN_TARGET,
    reader: Callable[[], dict[str, str]] | None = None,
) -> dict[str, str]:
    """Read ``PriorityAirc/LegionAdmin``. Never log the secret. Fail closed."""
    if reader is not None:
        got = reader() or {}
        user = str(got.get("username") or "").strip()
        pw = str(got.get("password") or "")
        if not user or not pw:
            raise LegionCredmanError("credman-missing")
        return {"username": user, "password": pw}
    # FR #5526: native CredReadW (no PowerShell timeout on missing targets).
    import airc_credman as _cred

    try:
        pair = _cred.read_generic_credential(target)
    except _cred.CredmanError as exc:
        raise LegionCredmanError(f"credman-read-failed:{exc.reason}") from exc
    if pair is None:
        raise LegionCredmanError("credman-missing")
    user = str(pair.username or "").strip()
    pw = str(pair.password or "")
    if not user or not pw:
        raise LegionCredmanError("credman-empty")
    return {"username": user, "password": pw}


def default_legion_credman() -> dict[str, str]:
    """Live CredMan ``PriorityAirc/LegionAdmin``. Empty dict means missing (fail closed)."""
    try:
        return read_legion_credman()
    except LegionCredmanError:
        return {}


def _candidate_version_from_msi_name(msi: Path) -> str:
    name = msi.stem
    if name.lower().startswith("airc-"):
        return name[5:]
    return name


def _resolve_legion_msi_path(spec: dict[str, Any]) -> Path:
    """Local path, allowed GitHub release URL, or Latest download (FR #5309 / #5382)."""
    from airc_network_installer.github_msi import download_latest_airc_msi
    from urllib.request import urlretrieve

    raw = (spec.get("msi") or "").strip()
    if not raw:
        dest = Path(str(spec.get("download_dir") or os.getcwd()))
        dest.mkdir(parents=True, exist_ok=True)
        msi_path, _tag = download_latest_airc_msi(dest)
        return msi_path
    if "://" in raw:
        if not _msi_allowed(raw):
            raise ValueError("foreign-msi-url")
        dest = Path(str(spec.get("download_dir") or os.getcwd()))
        dest.mkdir(parents=True, exist_ok=True)
        name = raw.rstrip("/").split("/")[-1] or "airc-download.msi"
        if not name.lower().endswith(".msi"):
            name = "airc-download.msi"
        out = dest / name
        urlretrieve(raw, out)  # noqa: S310 — allowlist-checked bobiverse release URL only
        return out
    return Path(raw)


def default_installer_run(spec: dict[str, Any], *, secret: str = "") -> dict[str, Any]:
    """Import-path invoke. WhatIf / dry_run never calls install_remote (FR #5382).

    FR #5529: secret is an explicit kwarg (or leftover env for older callers),
    never written into the service process environment.
    """
    from airc_network_installer.install import (
        install_local,
        install_remote,
        plan_psexec,
    )

    host = str((spec.get("hosts") or [""])[0] or "")
    dry = bool(spec.get("dry_run"))
    profile = str(spec.get("profile") or "client")
    force = bool(spec.get("force"))
    timeout_s = float(spec.get("timeout_s") or LEGION_TIMEOUT_S)
    if dry:
        # FR #5712: WhatIf plans PsExec like ensure_psexec (no download / no writes).
        pse_plan = plan_psexec(str(spec.get("psexec") or ""))
        raw_msi = (spec.get("msi") or "").strip()
        if raw_msi:
            try:
                msi_note = str(_resolve_legion_msi_path(spec))
            except Exception as exc:  # noqa: BLE001
                msi_note = f"msi-unresolved:{type(exc).__name__}"
        else:
            msi_note = "latest"
        base = {
            "host": host,
            "profile": profile,
            "force": force,
            "timeout_s": timeout_s,
            "msi": msi_note,
        }
        state = str(pse_plan.get("state") or "")
        if state in ("found", "cached"):
            return {
                **base,
                "ok": True,
                "status": "dry-run",
                "psexec": str(pse_plan.get("path") or ""),
            }
        if state == "would-download":
            return {
                **base,
                "ok": True,
                "status": "dry-run",
                "psexec": "would-download",
                "psexec_download": {
                    "url": str(pse_plan.get("url") or ""),
                    "dest": str(pse_plan.get("dest") or ""),
                },
            }
        if state == "unreachable":
            need = (
                "Sysinternals PsExec source unreachable: "
                f"{pse_plan.get('reason') or 'unreachable'} "
                f"url={pse_plan.get('url') or ''}"
            )
            return {
                **base,
                "ok": False,
                "status": "failed",
                "psexec": "psexec-source-unreachable",
                "error": "psexec-source-unreachable",
                "need": need,
                "psexec_download": {
                    "url": str(pse_plan.get("url") or ""),
                    "dest": str(pse_plan.get("dest") or ""),
                },
                "failures": [
                    {
                        "host": host,
                        "error": "psexec-source-unreachable",
                        "need": need,
                    }
                ],
            }
        # missing (opt-out) or unknown
        need = (
            "psexec on PATH or allow Sysinternals download to "
            "%ProgramData%\\bobiverse\\tools\\PsExec.exe "
            "(AIRC_LEGION_NO_PSEXEC_DOWNLOAD=1 disables download; "
            "MSI never bundles PsExec)"
        )
        return {
            **base,
            "ok": False,
            "status": "failed",
            "psexec": "psexec-missing",
            "error": "psexec-missing",
            "need": need,
            "failures": [{"host": host, "error": "psexec-missing", "need": need}],
        }

    try:
        msi_path = _resolve_legion_msi_path(spec)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "status": "failed",
            "host": host,
            "error": f"msi-resolve:{type(exc).__name__}",
        }
    if not msi_path.is_file():
        return {
            "ok": False,
            "status": "failed",
            "host": host,
            "error": "msi-missing",
        }

    password = secret or os.environ.get("AIRC_LEGION_PASSWORD", "")
    user = str(spec.get("username") or "")
    log_dir = Path(str(spec.get("log_dir") or "airc-install-logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    # FR #5655: download-on-demand when PATH has no PsExec (licence forbids MSI bundle).
    from airc_network_installer.install import ensure_psexec

    psexec = ensure_psexec(str(spec.get("psexec") or ""))
    if not psexec:
        need = (
            "psexec on PATH or allow Sysinternals download to "
            "%ProgramData%\\bobiverse\\tools\\PsExec.exe "
            "(AIRC_LEGION_NO_PSEXEC_DOWNLOAD=1 opts out; MSI never bundles PsExec)"
        )
        return {
            "ok": False,
            "status": "failed",
            "host": host,
            "error": "psexec-missing",
            "need": need,
            "psexec": "psexec-missing",
            "msi": str(msi_path),
            "log_dir": str(log_dir),
            "failures": [{"host": host, "error": "psexec-missing", "need": need}],
        }

    candidate = _candidate_version_from_msi_name(msi_path)
    local_names = {socket_hostname().lower(), "localhost", "127.0.0.1"}
    try:
        if host.lower() in local_names:
            row = install_local(
                msi_path=msi_path,
                candidate_version=candidate,
                profile=profile,
                force=force,
                log_dir=log_dir,
                dry_run=False,
            )
        else:
            row = install_remote(
                host=host,
                msi_path=msi_path,
                candidate_version=candidate,
                profile=profile,
                force=force,
                psexec=psexec,
                username=user,
                password=password,
                log_dir=log_dir,
                dry_run=False,
                timeout_s=timeout_s,
            )
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "status": "failed",
            "host": host,
            "error": f"install:{type(exc).__name__}",
            "msi": str(msi_path),
            "log_dir": str(log_dir),
        }

    status = str(getattr(row, "status", "") or "failed")
    ok = status in ("success", "reboot_required", "skipped", "dry-run")
    return {
        "ok": ok,
        "status": status,
        "host": host,
        "msi": str(msi_path),
        "action": getattr(row, "action", ""),
        "previous_version": getattr(row, "previous_version", ""),
        "detail": getattr(row, "detail", ""),
        "log_path": getattr(row, "log_path", ""),
        "username": user,
        "has_password": bool(password),
        "log_dir": str(log_dir),
        "profile": profile,
        "force": force,
        "timeout_s": timeout_s,
    }


def installer_legion_work(
    target: str,
    *,
    whatif: bool = False,
    run_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    credman: Callable[[], dict[str, str]] | None = None,
    msi: str | None = None,
    log_dir: str | None = None,
    **_kw: Any,
) -> dict[str, Any]:
    """FR #5309: one host, client profile, latest Release MSI, no --force."""
    if not _msi_allowed(msi):
        return {
            "ok": False,
            "target": target,
            "whatif": bool(whatif),
            "invoked_installer": False,
            "force": False,
            "timeout_s": LEGION_TIMEOUT_S,
            "profile": "client",
            "error": "foreign-msi-url",
        }
    # FR #5659: passed (DCC CRED) -> CredMan -> SYSTEM.
    import airc_identity as _ident
    import airc_passed_cred as _pcred

    sys_ident = legion_system_identity()
    cred_id = str(_kw.get("cred_id") or "").strip().lower()
    passed = _kw.get("passed_cred")
    if passed is None and cred_id:
        passed = _pcred.GLOBAL_PASSED_CREDS.take(cred_id)
    passed_requested = bool(cred_id) or bool(_kw.get("passed_requested"))
    if passed_requested and not (
        passed and str(passed.get("username") or "").strip() and str(passed.get("password") or "")
    ):
        return {
            "ok": False,
            "target": target,
            "whatif": bool(whatif),
            "invoked_installer": False,
            "force": False,
            "timeout_s": LEGION_TIMEOUT_S,
            "profile": "client",
            "error": "auth_failed",
            "identity": "passed",
            "identity_label": "passed (missing)",
            "failures": [{"host": target, "error": "auth_failed", "reason": "cred-missing"}],
        }

    def _reader(tgt: str) -> dict[str, str]:
        if credman is not None:
            return credman() or {}
        return _ident.default_credman_reader(tgt)

    resolved = _ident.resolve_remote_identity(
        verb="legion",
        passed=passed if isinstance(passed, dict) else None,
        passed_requested=False,
        credman_target=_CREDMAN_TARGET,
        credman_reader=_reader,
        system_fn=lambda: {
            "account": sys_ident["computer_account"],
            "username": sys_ident["computer_account"],
            "password": "",
        },
    )
    user = resolved.username if resolved.source != _ident.IDENTITY_SYSTEM else ""
    secret = resolved.password if resolved.source != _ident.IDENTITY_SYSTEM else ""
    use_secret = resolved.source in (_ident.IDENTITY_PASSED, _ident.IDENTITY_CREDMAN)
    spec: dict[str, Any] = {
        "hosts": [target],
        "profile": "client",
        "force": False,
        "timeout_s": LEGION_TIMEOUT_S,
        "dry_run": bool(whatif),
        "whatif": bool(whatif),
        "msi": (msi or "").strip(),
        "log_dir": log_dir or "airc-install-logs",
        "identity": resolved.source,
        "computer_account": sys_ident["computer_account"],
        "identity_label": resolved.label,
        "account": resolved.account,
    }
    if resolved.credman_target:
        spec["credman_target"] = resolved.credman_target
    if use_secret and user:
        spec["username"] = user
        spec["password_via"] = "passed" if resolved.source == _ident.IDENTITY_PASSED else "credman"
    # FR #5529: pass secret only as a runner kwarg, never os.environ.
    runner = run_fn or default_installer_run
    try:
        out = runner(spec, secret=secret) if use_secret else runner(spec)
    except TypeError:
        out = runner(spec)
    status = str((out or {}).get("status") or "")
    fails = list((out or {}).get("failures") or [])
    err = (out or {}).get("error")
    detail = str((out or {}).get("detail") or "")
    blob = " ".join(str(x) for x in (err, detail, status, fails))
    hint = ""
    if (not bool((out or {}).get("ok", True))) and _access_denied_reason(blob):
        if resolved.source in (_ident.IDENTITY_PASSED, _ident.IDENTITY_CREDMAN):
            # FR #5659: wrong non-SYSTEM identity fails closed (no silent fallback).
            err = "auth_failed"
            fails.append(
                {
                    "host": target,
                    "error": "auth_failed",
                    "identity": resolved.source,
                    "account": resolved.account,
                }
            )
        else:
            err = "system-access-denied"
            hint = _system_access_hint(sys_ident["computer_account"])
            fails.append({"host": target, "error": "system-access-denied", "hint": hint})
    body: dict[str, Any] = {
        "ok": bool((out or {}).get("ok", True)) and err not in ("auth_failed", "system-access-denied"),
        "target": target,
        "whatif": bool(whatif),
        "dry_run": bool(whatif),
        "invoked_installer": True,
        "force": False,
        "timeout_s": LEGION_TIMEOUT_S,
        "profile": "client",
        "hosts": [target],
        "status": status if err not in ("auth_failed",) else "failed",
        "log_dir": spec["log_dir"],
        "error": err,
        "failures": fails,
        "identity": resolved.source,
        "computer_account": sys_ident["computer_account"],
        "identity_label": resolved.label,
        "account": resolved.account,
    }
    # FR #5659: missing CredMan is logged, not a hard failure (falls through to SYSTEM).
    if resolved.credman_missing:
        body["credman_missing"] = True
        body["credman_fell_through"] = "system"
        if resolved.credman_error:
            body["credman_error"] = resolved.credman_error
    if hint:
        body["hint"] = hint
    if (out or {}).get("msi"):
        body["msi"] = (out or {}).get("msi")
    if (out or {}).get("psexec"):
        body["psexec"] = (out or {}).get("psexec")
    if (out or {}).get("need"):
        body["need"] = (out or {}).get("need")
    # FR #5655 / #5712: surface psexec provision failures even when runner only set error=.
    _pse_fail_errs = ("psexec-missing", "psexec-source-unreachable")
    if str(err or "") in _pse_fail_errs and not any(
        str(f.get("error") or "") in _pse_fail_errs for f in fails
    ):
        fails.append(
            {
                "host": target,
                "error": str(err),
                "need": body.get("need")
                or "psexec on PATH or ProgramData bobiverse tools download",
            }
        )
        body["failures"] = fails
        body["ok"] = False
        if not body.get("status"):
            body["status"] = "failed"
    if whatif:
        # Prefer runner-reported psexec; default label only for plan display.
        # Do not invent psexec-missing when the stub/runner omitted the key (MRB #5732).
        pse = body.get("psexec")
        plan_pse = pse if pse not in (None, "") else "psexec-missing"
        body["plan"] = {
            "target": target,
            "identity": spec["identity_label"],
            "msi": body.get("msi") or "latest",
            "psexec": plan_pse,
            "install": "skipped (whatif)",
        }
        dl = (out or {}).get("psexec_download")
        if isinstance(dl, dict):
            if dl.get("url"):
                body["plan"]["psexec_url"] = str(dl.get("url"))
            if dl.get("dest"):
                body["plan"]["psexec_dest"] = str(dl.get("dest"))
        # FR #5655 / #5712: fail WhatIf only when runner/error explicitly reported
        # missing or unreachable (not when the psexec key was absent).
        if str(err or "") in _pse_fail_errs or (
            pse is not None and str(pse) in _pse_fail_errs
        ):
            body["ok"] = False
            body["status"] = body.get("status") or "failed"
            body["plan"]["will_fail"] = str(err or pse)
    return body


def run_legion_verb(
    *,
    target: str = "",
    whatif: bool = False,
    job_id: str = "",
    worker: Callable[..., Any] | None = None,
    wait: bool = False,
    on_done: Callable[[LegionVerbResult], Any] | None = None,
    **_kw: Any,
) -> LegionVerbResult:
    qid = (job_id or "").strip().lower() or "00000000"
    work = worker or installer_legion_work
    extra = " whatif=1" if whatif else ""
    # FR #5583: accept only; DONE is last after out/CONT from deliver_*.
    accepted = (
        f"LEGION accepted id={qid} target={target} timeout={LEGION_TIMEOUT_S}{extra}"
    )
    work_kw: dict[str, Any] = {}
    if "credman" in _kw:
        work_kw["credman"] = _kw["credman"]
    # FR #5659: take DCC-staged cred in parent (isolated child has no shared stash).
    cred_id = str(_kw.get("cred_id") or "").strip().lower()
    if cred_id:
        work_kw["cred_id"] = cred_id
        if "passed_cred" not in _kw:
            try:
                import airc_passed_cred as _pcred

                taken = _pcred.GLOBAL_PASSED_CREDS.take(cred_id)
                if taken:
                    work_kw["passed_cred"] = taken
                work_kw["passed_requested"] = True
            except Exception:
                work_kw["passed_requested"] = True
    if "passed_cred" in _kw:
        work_kw["passed_cred"] = _kw["passed_cred"]
        work_kw["passed_requested"] = True
    if _kw.get("passed_requested"):
        work_kw["passed_requested"] = True
    force_thread = bool(work_kw.get("passed_cred") or work_kw.get("passed_requested"))

    def _finish(data: dict[str, Any], *, reply: str | None = None) -> LegionVerbResult:
        err = str(data.get("error") or "")
        fails = list(data.get("failures") or [])
        if not fails and err:
            fails = [{"host": data.get("target") or target, "error": err}]
        msi = str(data.get("msi") or "")
        psexec = str(data.get("psexec") or "")
        plan = data.get("plan") if isinstance(data.get("plan"), dict) else {}
        # FR #5530: surface WhatIf probe results even when worker only set top-level keys.
        ident_label = str(data.get("identity_label") or "")
        if whatif and not plan:
            plan = {
                "target": str(data.get("target") or target),
                "identity": ident_label or "SYSTEM",
                "msi": msi or "latest",
                "psexec": psexec or "psexec-missing",
                "install": "skipped (whatif)",
            }
        elif whatif and ident_label and "identity" not in plan:
            plan = {**plan, "identity": ident_label}
        res = LegionVerbResult(
            bool(data.get("ok", True)),
            reply or accepted,
            job_id=qid,
            status=str(data.get("status") or ""),
            error=err,
            failures=fails,
            msi=msi,
            psexec=psexec,
            plan=dict(plan),
            identity=str(data.get("identity") or ""),
            computer_account=str(data.get("computer_account") or ""),
            identity_label=ident_label,
        )
        if on_done is not None:
            on_done(res)
        return res

    def _call_work() -> dict[str, Any]:
        try:
            data = work(target, whatif=whatif, **work_kw)
        except TypeError:
            data = work(target=target, whatif=whatif, **work_kw)
        return data if isinstance(data, dict) else {}

    def _safe() -> LegionVerbResult:
        try:
            data = _call_work()
            return _finish(data)
        except Exception as exc:
            return _finish(
                {
                    "ok": False,
                    "target": target,
                    "error": type(exc).__name__,
                    "status": "",
                }
            )

    if wait:
        # FR #5389: CredRead lives here (or in installer_legion_work), not on accept.
        return _safe()
    import airc_isolated as _iso

    if _iso.is_packaged_work(work):

        def _from_child(data: Any) -> None:
            payload = data if isinstance(data, dict) else {}
            # FR #5665: normalize isolated death to worker_died + failures[].
            # FR #5659: missing CredMan falls through (no exit=126 here).
            if _iso.is_worker_fault(payload) or (
                isinstance(payload, dict)
                and payload.get("ok") is False
                and str(payload.get("error") or "").lower()
                in {"worker_died", "isolated-fault"}
            ):
                detail = str(
                    payload.get("detail") or payload.get("error") or "no-result"
                )[:300]
                payload = {
                    "ok": False,
                    "target": target,
                    "error": "worker_died",
                    "detail": detail,
                    "status": "failed",
                    "failures": [
                        {
                            "host": target,
                            "error": "worker_died",
                            "detail": detail,
                        }
                    ],
                }
            _finish(payload)

        if force_thread:
            # Passed secrets must not cross packaged IPC; stay in-process.
            threading.Thread(target=_safe, name="airc-legion-worker", daemon=True).start()
        else:
            _iso.start_isolated(
                wait=False,
                run=_call_work,
                packaged=(
                    "airc_legion",
                    "installer_legion_work",
                    {"target": target, "whatif": bool(whatif)},
                ),
                name="airc-legion-worker",
                on_done=_from_child,
            )
    else:
        threading.Thread(target=_safe, name="airc-legion-worker", daemon=True).start()
    return LegionVerbResult(True, accepted, job_id=qid)


_SECRET_KEY_RE = re.compile(r"(?i)pass|secret|token|pwd|cred")


def _scrub(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: _scrub(v)
            for k, v in obj.items()
            if not _SECRET_KEY_RE.search(str(k))
        }
    if isinstance(obj, list):
        return [_scrub(x) for x in obj]
    if isinstance(obj, str) and _SECRET_KEY_RE.search(obj) and "=" in obj:
        return "[redacted]"
    return obj


def build_legion_log(
    *,
    target: str = "",
    whatif: bool = False,
    summary: str = "",
    failures: list[dict] | None = None,
    extra: dict | None = None,
) -> dict[str, Any]:
    """FR #5311: installer log + failures[]; secrets stripped."""
    log: dict[str, Any] = {
        "target": target,
        "whatif": bool(whatif),
        "summary": summary,
        "failures": list(failures or []),
        "timeout_s": LEGION_TIMEOUT_S,
        "profile": "client",
        "force": False,
    }
    if extra:
        for k, v in extra.items():
            if not _SECRET_KEY_RE.search(str(k)):
                log[k] = v
    log = _scrub(log)
    log["failure_count"] = len(log.get("failures") or [])
    return log


def legion_log_bytes(log: dict[str, Any]) -> bytes:
    return (json.dumps(log, separators=(",", ":"), sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _done_identity_suffix(log: dict[str, Any]) -> str:
    """FR #5659 / #5711: delegate to shared airc_identity.done_identity_suffix."""
    import airc_identity as _ident

    return _ident.done_identity_suffix(log)


def deliver_legion_log(
    *,
    job_id: str,
    log: dict[str, Any],
    offer: Any | None = None,
    send_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    import airc_dcc_bulk as _dcc

    jid = (job_id or "").strip().lower() or "00000000"
    raw = legion_log_bytes(log)
    digest = hashlib.sha256(raw).hexdigest()
    nfail = int(log.get("failure_count") or 0)
    # FR #5655: non-zero DONE when failures[] or summary=failed (parity with EXTENSION FR #5644).
    summary_s = str(log.get("summary") or "").strip().lower()
    exit_code = 0 if nfail == 0 and summary_s not in ("failed", "fail") else 1
    summary = (
        f"LEGION log target={log.get('target')} failures={nfail} "
        f"bytes={len(raw)}"
    )
    lines: list[str] = [f"out id={jid} seq=1 {summary}"]
    for i, fail in enumerate(log.get("failures") or [], start=2):
        lines.append(
            f"out id={jid} seq={i} failure {json.dumps(fail, separators=(',', ':'))}"
        )
    if offer is not None:
        sender = send_fn or _dcc.send_offer_payload_bounded
        try:
            sender(raw, offer)
            done = _dcc.format_done_via_dcc(
                jid, exit_code, nbytes=len(raw), sha256=digest, via="dcc"
            ) + _done_identity_suffix(log)
            return {
                "via": "dcc",
                "sha256": digest,
                "nbytes": len(raw),
                "summary": summary,
                "lines": [lines[0], done],
                "done": done,
            }
        except Exception as exc:
            lines.append(
                f"err id={jid} seq={len(lines)+1} dcc failed: {exc}; falling back to IRC"
            )
            lines.append("CONT id=" + jid + " offset=1")
            done = f"DONE id={jid} exit={exit_code} via=irc reason=dcc-fail{_done_identity_suffix(log)}"
            lines.append(done)
            return {
                "via": "irc",
                "sha256": digest,
                "nbytes": len(raw),
                "summary": summary,
                "lines": lines,
                "done": done,
                "payload": raw,
            }
    lines.append("CONT id=" + jid + " offset=1")
    done = f"DONE id={jid} exit={exit_code} via=irc{_done_identity_suffix(log)}"
    lines.append(done)
    return {
        "via": "irc",
        "sha256": digest,
        "nbytes": len(raw),
        "summary": summary,
        "lines": lines,
        "done": done,
        "payload": raw,
    }
