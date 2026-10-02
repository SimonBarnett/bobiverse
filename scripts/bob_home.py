r"""Bobiverse home layout + one-time migration from the pre-0.1.15 ``~\.agentic-irc-*`` homes.

Homes (no agentic_irc dependency):
  chair home   BOB_HOME           default ``~/.jeeves``      (Jeeves identity, operators, accounts)
  digest home  BOB_DIGEST_HOME    default ``~/.bobiverse``   (digest.json, registered-machines.json ...)
  config dir   BOB_CONFIG_DIR     default ``<install>/config`` (optional github.token, chair oper.cred)

``migrate_legacy`` COPIES the old home into the new one (never overwrites, never deletes) and
drops a marker, so the old home stays as a backup and the migration runs once. Secret values
are never printed; only file names and counts are reported.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

MARKER = ".migrated-from-legacy.json"
CHAIR_NAME = ".jeeves"
DIGEST_NAME = ".bobiverse"
LEGACY_CHAIR_NAME = ".agentic-irc-jeeves"
LEGACY_DIGEST_NAME = ".agentic-irc-bobiverse"
# never carried over: live state of the old process (.pos sealed specially for outboxes — FR #68)
SKIP_SUFFIXES = (".log", ".pid", ".lock", ".tmp", ".pos")
SKIP_NAMES = {".agentic-irc-service-start", ".bobiverse-service-start", "agent.quit.request", MARKER}
SECRET_NAMES = ("report.secret", "github.token", "nickserv.password", "identity.json")
# the files the fleet cares about most (reported by name in the migration summary)
KEY_FILES = ("digest.json", "focus.json", "ignored.json", "queue.json", "registered-machines.json")
# outbox basenames that need a companion cursor after migrate (FR #68)
OUTBOX_BASENAMES = ("chair-outbox.txt", "outbox.txt")


def _admin_profile() -> Path:
    drive = (os.environ.get("SystemDrive") or "C:").rstrip("\\/")
    return Path(drive + os.sep) / "Users" / "Administrator"


def _profile() -> Path:
    raw = (os.environ.get("USERPROFILE") or os.environ.get("HOME") or "").strip()
    return Path(raw) if raw else Path.home()


def chair_home() -> Path:
    raw = (os.environ.get("BOB_HOME") or "").strip()
    return Path(raw).expanduser() if raw else _profile() / CHAIR_NAME


def digest_home() -> Path:
    raw = (os.environ.get("BOB_DIGEST_HOME") or "").strip()
    return Path(raw).expanduser() if raw else _profile() / DIGEST_NAME


def install_root() -> Path:
    """<InstallRoot> when running from <InstallRoot>\\scripts (jeeves/bob MSI layout)."""
    return Path(__file__).resolve().parent.parent


def config_dir() -> Path:
    raw = (os.environ.get("BOB_CONFIG_DIR") or "").strip()
    return Path(raw).expanduser() if raw else install_root() / "config"


def legacy_candidates(new_home: Path, role: str = "") -> list[Path]:
    """Old homes that may hold this role's data: same profile dir, then the Administrator profile.

    ``role`` is ``chair`` | ``digest`` (else inferred from the new home's folder name, so a custom
    location such as ``<install>\\home-jeeves`` still needs an explicit role).
    """
    new_home = Path(new_home)
    name = new_home.name.lower()
    if role == "chair" or name == CHAIR_NAME:
        legacy = LEGACY_CHAIR_NAME
    elif role == "digest" or name == DIGEST_NAME:
        legacy = LEGACY_DIGEST_NAME
    else:
        return []
    out: list[Path] = []
    for base in (new_home.parent, _profile(), _admin_profile()):
        cand = Path(base) / legacy
        if cand not in out and cand.resolve() != new_home.resolve():
            out.append(cand)
    return out


def _skip(p: Path) -> bool:
    n = p.name
    return n in SKIP_NAMES or n.lower().endswith(SKIP_SUFFIXES)


def _is_outbox_file(name: str) -> bool:
    n = name.lower()
    return n in OUTBOX_BASENAMES or n.endswith("outbox.txt")


def _seal_outbox_cursors(old: Path, new_home: Path, stats: dict) -> None:
    """FR #68: after copying outbox bodies, restore or invent ``*.pos`` cursors.

    ``SKIP_SUFFIXES`` drops live ``.pos`` files. Without a cursor, ``load_outbox_pos``
    returns 0 and the chair replays the whole backlog (flood-starving +o / ChanServ).
    Prefer the legacy cursor when present; otherwise seal at EOF so history is not resent.
    """
    sealed: list[str] = stats.setdefault("outbox_pos_sealed", [])
    old = Path(old)
    new_home = Path(new_home)
    for entry in sorted(new_home.iterdir()):
        if not entry.is_file() or not _is_outbox_file(entry.name):
            continue
        pos_name = entry.name + ".pos"
        dest_pos = new_home / pos_name
        if dest_pos.is_file():
            continue
        candidates = [
            old / pos_name,
            old / (entry.stem + ".pos"),  # chair-outbox.pos next to chair-outbox.txt
        ]
        copied = False
        for src_pos in candidates:
            if src_pos.is_file():
                try:
                    shutil.copy2(src_pos, dest_pos)
                    sealed.append(pos_name)
                    copied = True
                    break
                except OSError as exc:
                    stats.setdefault("errors", []).append(f"{pos_name}: {type(exc).__name__}")
        if copied:
            continue
        try:
            dest_pos.write_text(str(entry.stat().st_size) + "\n", encoding="utf-8")
            sealed.append(pos_name)
        except OSError as exc:
            stats.setdefault("errors", []).append(f"{pos_name}: {type(exc).__name__}")


def _copy_tree(src: Path, dst: Path, stats: dict) -> None:
    for entry in sorted(src.iterdir()):
        if _skip(entry):
            continue
        target = dst / entry.name
        try:
            if entry.is_dir():
                if entry.name == "__pycache__":
                    continue
                target.mkdir(parents=True, exist_ok=True)
                _copy_tree(entry, target, stats)
            elif entry.is_file():
                if target.exists():
                    stats["kept"] += 1
                    try:  # never lose the old copy when the new home already has a different file
                        if target.read_bytes() != entry.read_bytes():
                            shutil.copy2(entry, target.with_name(entry.name + ".legacy"))
                            stats["conflicts"].append(entry.name)
                    except OSError:
                        pass
                    continue
                shutil.copy2(entry, target)
                stats["copied"] += 1
                stats["names"].append(entry.name)
        except OSError as exc:
            stats["errors"].append(f"{entry.name}: {type(exc).__name__}")


def migrate_legacy(new_home: Path, old_homes: list[Path] | None = None, role: str = "") -> dict:
    """Copy the first existing legacy home into ``new_home`` once. Returns a summary dict.

    ``status``: ``migrated`` | ``already`` (marker present) | ``no-legacy`` | ``error``.
    """
    new_home = Path(new_home)
    marker = new_home / MARKER
    if marker.is_file():
        return {"status": "already", "new": str(new_home)}
    cands = old_homes if old_homes is not None else legacy_candidates(new_home, role)
    old = next((c for c in cands if Path(c).is_dir()), None)
    if old is None:
        return {"status": "no-legacy", "new": str(new_home)}
    new_home.mkdir(parents=True, exist_ok=True)
    stats = {
        "copied": 0,
        "kept": 0,
        "names": [],
        "errors": [],
        "conflicts": [],
        "outbox_pos_sealed": [],
    }
    _copy_tree(Path(old), new_home, stats)
    _seal_outbox_cursors(Path(old), new_home, stats)
    summary = {
        "status": "error" if stats["errors"] and not stats["copied"] else "migrated",
        "old": str(old),
        "new": str(new_home),
        "copied": stats["copied"],
        "kept_existing": stats["kept"],
        "key_files": [n for n in KEY_FILES if n in stats["names"]],
        "secret_files": [n for n in SECRET_NAMES if n in stats["names"]],
        "outbox_pos_sealed": list(stats.get("outbox_pos_sealed") or [])[:20],
        "conflicts": stats["conflicts"][:20],
        "errors": stats["errors"][:10],
        "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "note": "old home left untouched as backup",
    }
    if summary["status"] == "migrated":
        try:
            marker.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass
    return summary


def migrate_secrets_to_config(
    cfg: Path, profiles: list[Path] | None = None, homes: list[Path] | None = None
) -> list[str]:
    """Copy the OPTIONAL github.token into the install config dir from ``<profile>\\.grok\\bob``
    or from the (migrated) chair/digest homes. (v0.1.16: report.secret is no longer used or copied.)

    Never overwrites. Returns the names copied (values are never read into logs).
    """
    cfg = Path(cfg)
    got: list[str] = []
    profs = profiles if profiles is not None else [
        _profile(),
        _admin_profile(),
    ]
    for name in ("github.token",):
        dst = cfg / name
        if dst.is_file():
            continue
        sources = [Path(prof) / ".grok" / "bob" / name for prof in profs]
        sources += [Path(h) / name for h in (homes or [])]
        for src in sources:
            if src.is_file():
                cfg.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(src, dst)
                    got.append(name)
                except OSError:
                    continue
                break
    return got


def ensure_homes(chair: Path | None = None, digest: Path | None = None, log=print) -> list[dict]:
    """First-start hook: migrate chair + digest homes (idempotent)."""
    out = []
    for h, role in ((chair, "chair"), (digest, "digest")):
        if h is None:
            continue
        res = migrate_legacy(Path(h), role=role)
        out.append(res)
        if res["status"] == "migrated":
            log(
                f"INFO home-migration {res['old']} -> {res['new']} copied={res['copied']} "
                f"key={','.join(res['key_files']) or '-'} secrets={','.join(res['secret_files']) or '-'} "
                "(old home kept as backup)"
            )
        elif res["status"] == "error":
            log(f"WARN home-migration {res.get('old')} -> {res['new']} errors={res['errors']}")
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="bobiverse home migration")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("migrate")
    m.add_argument("--chair-home", default="")
    m.add_argument("--digest-home", default="")
    m.add_argument("--config-dir", default="")
    a = ap.parse_args(argv)
    chair = Path(a.chair_home) if a.chair_home else None
    digest = Path(a.digest_home) if a.digest_home else None
    ensure_homes(chair, digest)
    if a.config_dir:
        names = migrate_secrets_to_config(Path(a.config_dir), homes=[h for h in (chair, digest) if h])
        if names:
            print(f"INFO config secrets copied from .grok\\bob: {','.join(names)} -> {a.config_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
