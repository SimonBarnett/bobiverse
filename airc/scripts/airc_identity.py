"""FR #5659: remote identity order for LEGION / EXTENSION / NETWORK.

Order: passed-in (DCC-staged) -> CredMan -> SYSTEM / computer account.
Never log or return the password in labels. Wrong passed creds fail closed
(auth_failed) with no silent fallback.
"""
from __future__ import annotations

import re
import socket
from dataclasses import dataclass
from typing import Any, Callable

IDENTITY_PASSED = "passed"
IDENTITY_CREDMAN = "credman"
IDENTITY_SYSTEM = "system"

DEFAULT_TARGETS = {
    "legion": "PriorityAirc/LegionAdmin",
    "extension": "PriorityAirc/ExtensionAdmin",
    "network": "PriorityAirc/NetworkAdmin",
}

# FR #5745: optional airc.json credman_targets overrides (verb -> CredMan target).
_CONFIGURED_TARGETS: dict[str, str] = {}


def configure_credman_targets(cfg: dict[str, Any] | None) -> None:
    """Load ``credman_targets`` from airc.json (or clear when cfg is None/empty)."""
    global _CONFIGURED_TARGETS
    out: dict[str, str] = {}
    raw = (cfg or {}).get("credman_targets") if isinstance(cfg, dict) else None
    if isinstance(raw, dict):
        for verb in ("legion", "extension", "network"):
            val = str(raw.get(verb) or "").strip()
            if val:
                out[verb] = val
    _CONFIGURED_TARGETS = out


def credman_target_for(verb: str, *, override: str | None = None) -> str:
    """FR #5659 / #5745: per-verb CredMan target (override -> airc.json -> default)."""
    if override is not None and str(override).strip():
        return str(override).strip()
    key = (verb or "").strip().lower()
    return (_CONFIGURED_TARGETS.get(key) or DEFAULT_TARGETS.get(key) or "").strip()


@dataclass
class ResolvedIdentity:
    source: str  # passed|credman|system
    username: str
    password: str
    account: str
    label: str
    credman_target: str = ""
    credman_missing: bool = False
    credman_error: str = ""

    def identity_reason(self) -> str:
        """FR #5745: why SYSTEM was chosen after CredMan miss/error (empty otherwise)."""
        if not self.credman_missing:
            return ""
        if self.credman_error:
            return f"credman-read-error:{self.credman_error}"
        if self.credman_target:
            return f"credman-missing:{self.credman_target}"
        return "credman-missing"

    def public_dict(self) -> dict[str, Any]:
        """Safe for IRC / DCC logs (no secret)."""
        out: dict[str, Any] = {
            "identity": self.source,
            "account": self.account,
            "identity_label": self.label,
        }
        if self.credman_target:
            out["credman_target"] = self.credman_target
        if self.credman_missing:
            out["credman_missing"] = True
        if self.credman_error:
            out["credman_error"] = self.credman_error
        reason = self.identity_reason()
        if reason and self.source == IDENTITY_SYSTEM:
            out["identity_reason"] = reason
        return out


def format_identity_fallback_log(*, verb: str, resolved: ResolvedIdentity) -> str | None:
    """FR #5745: one-line console log when CredMan miss falls through to SYSTEM."""
    if resolved.source != IDENTITY_SYSTEM or not resolved.credman_missing:
        return None
    reason = resolved.identity_reason() or "credman-missing"
    acct = (resolved.account or "").strip() or "-"
    tgt = (resolved.credman_target or "").strip() or "-"
    return (
        f"identity-fallback verb={(verb or '-').lower()} reason={reason} "
        f"identity=system account={acct} target={tgt}"
    )


def system_computer_account(
    *,
    hostname_fn: Callable[[], str] | None = None,
    domain_fn: Callable[[], str] | None = None,
) -> dict[str, str]:
    host = str((hostname_fn or socket.gethostname)() or "LOCAL").split(".")[0]
    host = re.sub(r"[^A-Za-z0-9\-]", "", host).upper() or "LOCAL"
    import os

    domain = str((domain_fn or (lambda: os.environ.get("USERDOMAIN") or ""))() or "")
    domain = re.sub(r"[^A-Za-z0-9\-]", "", domain).upper()
    if domain and domain not in ("WORKGROUP", host):
        acct = f"{domain}\\{host}$"
    else:
        acct = f"{host}$"
    return {"account": acct, "username": acct, "password": ""}


def default_credman_reader(target: str) -> dict[str, str]:
    """Read CredMan pair; empty dict means missing."""
    try:
        import airc_credman as _cred

        pair = _cred.read_generic_credential(target)
        if pair is None:
            return {}
        user = str(pair.username or "").strip()
        pw = str(pair.password or "")
        if not user or not pw:
            return {}
        return {"username": user, "password": pw}
    except Exception as exc:  # noqa: BLE001
        reason = getattr(exc, "reason", None) or type(exc).__name__
        return {"__error__": str(reason)}


def resolve_remote_identity(
    *,
    verb: str = "legion",
    passed: dict[str, str] | None = None,
    passed_requested: bool = False,
    credman_target: str | None = None,
    credman_reader: Callable[[str], dict[str, str]] | None = None,
    system_fn: Callable[[], dict[str, str]] | None = None,
) -> ResolvedIdentity:
    """Pick identity: passed -> CredMan -> SYSTEM.

    If ``passed_requested`` and passed is missing/empty -> auth_failed caller side.
    If ``passed`` is provided, it wins (caller must not fall back on auth failure).
    """
    target = credman_target_for(verb, override=credman_target)
    if passed is not None:
        user = str(passed.get("username") or "").strip()
        pw = str(passed.get("password") or "")
        if user and pw:
            return ResolvedIdentity(
                source=IDENTITY_PASSED,
                username=user,
                password=pw,
                account=user,
                label=f"passed ({user})",
                credman_target=target,
            )
        if passed_requested:
            return ResolvedIdentity(
                source=IDENTITY_PASSED,
                username="",
                password="",
                account="",
                label="passed (missing)",
                credman_target=target,
            )

    reader = credman_reader or default_credman_reader
    credman_missing = False
    credman_error = ""
    if target:
        got = reader(target) or {}
        if got.get("__error__"):
            credman_missing = True
            credman_error = str(got.get("__error__") or "credman-error")
        else:
            user = str(got.get("username") or "").strip()
            pw = str(got.get("password") or "")
            if user and pw:
                return ResolvedIdentity(
                    source=IDENTITY_CREDMAN,
                    username=user,
                    password=pw,
                    account=user,
                    label=f"credman ({user})",
                    credman_target=target,
                )
            credman_missing = True

    sys_fn = system_fn or system_computer_account
    sys = sys_fn() or {}
    acct = str(sys.get("account") or sys.get("username") or "").strip() or "LOCAL$"
    return ResolvedIdentity(
        source=IDENTITY_SYSTEM,
        username=str(sys.get("username") or acct),
        password=str(sys.get("password") or ""),
        account=acct,
        label=f"system ({acct})",
        credman_target=target,
        credman_missing=credman_missing,
        credman_error=credman_error,
    )


_SECRET_IRC_RE = re.compile(
    r"(?i)(?:^|\s)(?:pass(?:word)?|pwd|secret)\s*=\s*\S+"
)
_USER_IRC_RE = re.compile(r"(?i)(?:^|\s)(?:user(?:name)?)\s*=\s*\S+")


def irc_line_has_plaintext_secret(text: str) -> bool:
    """True when IRC text tries to pass password= (forbidden; use DCC CRED)."""
    return bool(_SECRET_IRC_RE.search(text or ""))


def irc_line_has_inline_userpass(text: str) -> bool:
    """True when both user= and pass= appear on IRC (reject)."""
    t = text or ""
    return bool(_USER_IRC_RE.search(t) and _SECRET_IRC_RE.search(t))

def done_identity_suffix(log: dict[str, Any]) -> str:
    """FR #5659 / #5711: DONE carries identity=passed|credman|system and account (never secret).

    Shared by LEGION and NETWORK so the wire format stays one formatter.
    """
    parts: list[str] = []
    ident = str(log.get("identity_source") or log.get("identity") or "").strip()
    if ident.lower() in ("passed", "credman", "system"):
        parts.append(f"identity={ident.lower()}")
    elif ident:
        tok = ident.split()[0].strip("()").lower()
        if tok in ("passed", "credman", "system"):
            parts.append(f"identity={tok}")
    acct = str(log.get("account") or "").strip()
    if acct and "password" not in acct.lower():
        parts.append(f"account={acct}")
    return (" " + " ".join(parts)) if parts else ""

