"""Jeeves chair: IRC operator login + channel-operator (+o) upkeep + visibility of what Ergo allows.

* Credentials live in the INSTALL config (``<install>/config/oper.cred``), DPAPI-protected
  (machine scope, so the installer account and the service account both work). They are
  provisioned by ``Install-Jeeves.ps1`` from an existing ergo-oper file or a prompt-less
  parameter. Values are never printed or logged.
* ``OPER <name> <password>`` is sent on connect; success is RPL_YOUREOPER (381) or user mode
  ``+o``; failure (491/464/481 while pending) is logged loudly.
* ``ChanServ LIST`` needs the Ergo oper capability ``chanreg`` (``oper-classes`` in ircd.yaml).
  This module only classifies the outcome; it never edits Ergo.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import protect

CRED_NAME = "oper.cred"
CRED_ENV = "BOB_OPER_FILE"
DEFAULT_OPER_NAME = "admin"

# What Simon must add to ircd.yaml when LIST is denied (printed verbatim by the chair).
CHANREG_HINT = (
    'ircd.yaml -> oper-classes -> "<the class of oper %s>" -> capabilities: add the line  - "chanreg"  '
    '(the stock "server-admin" class already has it; or set the oper\'s `class:` to "server-admin"), '
    "then /REHASH. Jeeves does not edit Ergo."
)


def cred_path(config_dir: Path) -> Path:
    env = (os.environ.get(CRED_ENV) or "").strip()
    return Path(env).expanduser() if env else Path(config_dir) / CRED_NAME


def write_credentials(path: Path, name: str, password: str) -> Path:
    name, password = (name or "").strip(), (password or "").strip()
    if not name or not password or "\n" in name + password or "\r" in name + password:
        raise ValueError("oper name/password empty or multi-line")
    protect.write_secret_bytes(Path(path), f"{name}\n{password}\n".encode("utf-8"), machine=True)
    return Path(path)


def load_credentials(path: Path) -> tuple[str, str] | None:
    try:
        raw = protect.read_secret_bytes(Path(path)).decode("utf-8-sig")
    except (OSError, ValueError):
        return None
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if len(lines) < 2:
        return None
    return lines[0], lines[1]


_OPER_LINE = re.compile(r"(?im)^\s*/?oper\s+(\S+)\s+(\S+)\s*$")


def parse_oper_file(text: str, default_name: str = DEFAULT_OPER_NAME) -> tuple[str, str] | None:
    """Understand an existing ergo-oper file: a ``/OPER <name> <password>`` line, else a lone token."""
    m = _OPER_LINE.search(text or "")
    if m and not m.group(2).startswith("<"):
        return m.group(1), m.group(2)
    toks = [ln.strip() for ln in (text or "").splitlines() if ln.strip() and " " not in ln.strip()]
    if len(toks) == 1:
        return default_name, toks[0]
    return None


def discover_oper_files(profiles: list[Path] | None = None) -> list[Path]:
    profs = profiles
    if profs is None:
        profs = []
        for raw in (os.environ.get("USERPROFILE"), os.environ.get("HOME")):
            if raw:
                profs.append(Path(raw))
        profs.append(Path(os.environ.get("SystemDrive") or "C:" + os.sep) / "Users" / "Administrator")
    out: list[Path] = []
    for prof in profs:
        for sub in ("Desktop", ".grok/ergo", ""):
            d = Path(prof) / sub if sub else Path(prof)
            try:
                for p in sorted(d.glob("ergo-oper*.txt")) + sorted(d.glob("ergo-oper*.password")) + sorted(d.glob("oper.password")):
                    if p not in out:
                        out.append(p)
            except OSError:
                continue
    return out


def provision(
    config_dir: Path,
    *,
    name: str = "",
    password: str = "",
    oper_file: str = "",
    profiles: list[Path] | None = None,
) -> dict:
    """Create ``oper.cred``. Returns a status dict WITHOUT any secret value.

    Order: explicit name+password, explicit file, existing cred (kept), discovered ergo-oper file.
    """
    target = cred_path(config_dir)
    if name and password:
        write_credentials(target, name, password)
        return {"status": "provisioned", "source": "parameter", "name": name, "path": str(target)}
    if oper_file:
        parsed = parse_oper_file(Path(oper_file).read_text(encoding="utf-8-sig", errors="replace"), name or DEFAULT_OPER_NAME)
        if not parsed:
            return {"status": "unparseable", "source": str(oper_file), "path": str(target)}
        write_credentials(target, parsed[0], parsed[1])
        return {"status": "provisioned", "source": str(oper_file), "name": parsed[0], "path": str(target)}
    existing = load_credentials(target) if target.is_file() else None
    if existing:
        return {"status": "kept", "name": existing[0], "path": str(target)}
    for cand in discover_oper_files(profiles):
        try:
            parsed = parse_oper_file(cand.read_text(encoding="utf-8-sig", errors="replace"), name or DEFAULT_OPER_NAME)
        except OSError:
            continue
        if parsed:
            write_credentials(target, parsed[0], parsed[1])
            return {"status": "provisioned", "source": str(cand), "name": parsed[0], "path": str(target)}
    return {"status": "missing", "path": str(target)}


# ---------------------------------------------------------------- wire parsing (pure)

_JUNK = {ord(c): None for c in "\ufeff\u200b\u200c\u200d\u2060\u00a0\x00"}


def _c(s) -> str:
    """BOM / zero-width / whitespace-safe token (v0.1.19: a stray U+FEFF must not hide our own +o)."""
    return str(s or "").translate(_JUNK).strip()


def names_has_op(parts: list[str], trailing: str, nick: str) -> tuple[str, bool] | None:
    """``353 <me> = #chan :@a +b me`` -> (channel, I am @-or-higher)."""
    if len(parts) < 4:
        return None
    chan = next((_c(p) for p in parts[2:5] if _c(p).startswith("#")), "")
    if not chan:
        return None
    me = _c(nick).lower()
    for tok in _c(trailing).split():
        tok = _c(tok)
        pref = ""
        while tok and tok[0] in "~&@%+":
            pref += tok[0]
            tok = tok[1:]
        tok = _c(tok.split("!", 1)[0])
        if tok.lower() == me:
            return chan, any(c in pref for c in "~&@")
    return chan, False


def mode_changes_for(parts: list[str], nick: str) -> list[tuple[str, str, bool]]:
    """``MODE #chan +o me`` -> [(channel, mode, added)] for the entries that target ``nick``."""
    if len(parts) < 4 or not _c(parts[1]).startswith("#"):
        return []
    chan, modestr, args = _c(parts[1]), _c(parts[2]).lstrip(":"), [_c(a).lstrip(":") for a in parts[3:]]
    out: list[tuple[str, str, bool]] = []
    add = True
    ai = 0
    takes_arg = set("ovhaqbeIklf")
    for ch in modestr:
        if ch == "+":
            add = True
        elif ch == "-":
            add = False
        elif ch in takes_arg:
            arg = args[ai] if ai < len(args) else ""
            ai += 1
            if ch in "ovhaq" and arg.lower() == _c(nick).lower():
                out.append((chan, ch, add))
    return out


def umode_has_o(modes: str) -> bool:
    """``+iZo`` / ``:+o`` / ``-o`` -> final state of ``o``."""
    state = None
    add = True
    for ch in modes.lstrip(":"):
        if ch == "+":
            add = True
        elif ch == "-":
            add = False
        elif ch == "o":
            state = add
    return bool(state)


def main(argv: list[str] | None = None) -> int:
    """``chair_oper.py provision --config-dir D [--oper-file F] [--name N]``.

    The password (parameter path) is taken from env ``BOB_OPER_PASSWORD`` - never from argv - and
    only status is printed (no secret values).
    """
    import argparse

    ap = argparse.ArgumentParser(description="provision Jeeves oper credentials")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pv = sub.add_parser("provision")
    pv.add_argument("--config-dir", required=True)
    pv.add_argument("--oper-file", default="")
    pv.add_argument("--name", default="")
    a = ap.parse_args(argv)
    res = provision(
        Path(a.config_dir),
        name=a.name,
        password=(os.environ.get("BOB_OPER_PASSWORD") or ""),
        oper_file=a.oper_file,
    )
    st = res["status"]
    where = res.get("source", "")
    print(f"INFO oper credentials {st} name={res.get('name', '-')} file={res['path']} {('from ' + where) if where else ''}".rstrip())
    if st in ("missing", "unparseable"):
        print(
            "WARN Jeeves will NOT be an IRC operator until oper credentials exist: re-run "
            "Install-Jeeves.ps1 -OperFile <file> (or -OperName/-OperPassword)."
        )
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
