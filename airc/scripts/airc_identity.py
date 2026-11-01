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


def configured_credman_targets(value: Any) -> dict[str, str]:
    targets = dict(DEFAULT_TARGETS)
    if isinstance(value, dict):
        for verb in targets:
            target = value.get(verb)
            if isinstance(target, str) and target.strip() and not any(
                ord(c) < 32 or ord(c) == 127 for c in target
            ):
                targets[verb] = target.strip()
    return targets


def _credman_error_code(value: Any) -> str:
    code = str(value or "")
    if re.fullmatch(r"(?:winerror-\d+|\d+|unsupported-platform)", code):
        return code
    return "read-failed"


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
    identity_reason: str = ""

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
        if self.identity_reason:
            out["identity_reason"] = self.identity_reason
        return out


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
        return {"__error__": _credman_error_code(getattr(exc, "reason", None))}


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
    target = (credman_target or DEFAULT_TARGETS.get((verb or "").lower(), "")).strip()
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
        try:
            got = reader(target) or {}
        except Exception as exc:
            got = {"__error__": _credman_error_code(getattr(exc, "reason", None))}
        if got.get("__error__"):
            credman_missing = True
            credman_error = _credman_error_code(got.get("__error__"))
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
        identity_reason=(
            f"credman-read-error:{credman_error}" if credman_error
            else f"credman-missing:{target}" if credman_missing else ""
        ),
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

    Shared by LEGION, EXTENSION and NETWORK so the wire format stays one formatter.
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
