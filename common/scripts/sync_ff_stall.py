"""FR #6773: one deduped stall intake when install sync ff-only fails.

First failure POSTs intake (crash-sig:sync-ff-failed:<machine>).
Repeat failures comment on the open issue (gh) using saved number / search.
Never puts secrets or config body into title/body.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

DEFAULT_REPO = "SimonBarnett/bobiverse"
_SIG_RE = re.compile(r"crash-sig:sync-ff-failed:([a-z0-9_.-]+)", re.I)


def state_dir() -> Path:
    override = (os.environ.get("BOB_SYNC_STALL_DIR") or "").strip()
    if override:
        p = Path(override)
        p.mkdir(parents=True, exist_ok=True)
        return p
    base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or ".")
    p = base / "Bobiverse" / "sync-ff-stall"
    p.mkdir(parents=True, exist_ok=True)
    return p


def machine_id(explicit: str | None = None) -> str:
    if explicit and str(explicit).strip():
        return str(explicit).strip().lower()
    for key in ("BOB_MACHINE_ID", "COMPUTERNAME"):
        v = (os.environ.get(key) or "").strip()
        if v:
            return v.lower()
    return "unknown"


def sync_sig(machine: str) -> str:
    mid = machine_id(machine)
    return f"sync-ff-failed:{mid}"


def _state_path(machine: str) -> Path:
    return state_dir() / f"{machine_id(machine)}.json"


def _load_state(machine: str) -> dict[str, Any]:
    path = _state_path(machine)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(machine: str, doc: dict[str, Any]) -> None:
    path = _state_path(machine)
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def format_sync_field(behind: int, reason: str) -> str:
    """Digest sync field: 'behind N, reason' — never secrets."""
    b = max(0, int(behind) if behind is not None else 0)
    why = _sanitize_reason(reason)
    return f"behind {b}, {why}"


def _sanitize_reason(reason: str) -> str:
    text = (reason or "").strip()
    # Drop anything that looks like a secret assignment or long blob.
    text = re.sub(r"(?i)(password|token|secret|api[_-]?key)\s*[:=]\s*\S+", r"\1=***", text)
    text = re.sub(r"\s+", " ", text)
    if len(text) > 160:
        text = text[:157] + "..."
    if not text:
        text = "ff-only not possible"
    return text


def _post(title: str, body: str, *, repo: str, sig: str) -> dict[str, Any]:
    import crash_report

    return crash_report._post_intake(title, body, repo=repo, sig=sig, exe="sync-ff")


def _gh_search_open(repo: str, sig: str) -> int | None:
    try:
        import shutil
        import subprocess

        if not shutil.which("gh"):
            return None
        proc = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                repo,
                "--state",
                "open",
                "--search",
                f"crash-sig:{sig}",
                "--json",
                "number,body,title",
                "--limit",
                "20",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=12,
            check=False,
        )
        if proc.returncode != 0:
            return None
        rows = json.loads(proc.stdout or "[]")
        for row in rows:
            blob = f"{row.get('title') or ''}\n{row.get('body') or ''}"
            if sig.lower() in blob.lower() or _SIG_RE.search(blob):
                return int(row["number"])
        return None
    except Exception:
        return None


def _gh_comment(repo: str, number: int, body: str) -> bool:
    try:
        import shutil
        import subprocess

        if not shutil.which("gh"):
            return False
        proc = subprocess.run(
            ["gh", "issue", "comment", str(number), "--repo", repo, "--body", body[:6000]],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
        return proc.returncode == 0
    except Exception:
        return False


def report(
    *,
    behind: int,
    reason: str,
    machine: str | None = None,
    repo: str = DEFAULT_REPO,
    filer_post: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """File or comment one sync-ff stall. Never raises."""
    try:
        mid = machine_id(machine)
        sig = sync_sig(mid)
        sync_field = format_sync_field(behind, reason)
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        title = f"stall: sync-ff-failed {mid}"[:200]
        body = (
            f"what: install worktree fast-forward failed; machine may run stale code\n"
            f"where: machine=`{mid}`\n"
            f"sync: {sync_field}\n"
            f"crash-sig:{sig}\n"
            f"fail-sig:{sig}\n"
            f"seen: {now}\n"
            f"\n---\n_via-sync-ff-stall FR=#6773_\n"
        )
        state = _load_state(mid)
        number = state.get("number")
        try:
            number = int(number) if number is not None else None
        except (TypeError, ValueError):
            number = None
        dry = (os.environ.get("BOB_SYNC_STALL_DRY") or "").strip() == "1"
        if number is None and not dry:
            number = _gh_search_open(repo, sig)
        if number is not None:
            if (os.environ.get("BOB_SYNC_STALL_DRY") or "").strip() == "1":
                ok = True
            else:
                ok = _gh_comment(repo, int(number), body)
            count = int(state.get("count") or 1) + 1
            _save_state(
                mid,
                {
                    "number": int(number),
                    "sig": sig,
                    "count": count,
                    "last_seen": now,
                    "sync": sync_field,
                    "first_seen": state.get("first_seen") or now,
                },
            )
            return {
                "ok": bool(ok),
                "deduped": True,
                "number": int(number),
                "sig": sig,
                "sync": sync_field,
                "count": count,
            }
        if (os.environ.get("BOB_SYNC_STALL_DRY") or "").strip() == "1":
            _save_state(
                mid,
                {
                    "number": None,
                    "sig": sig,
                    "count": 1,
                    "first_seen": now,
                    "last_seen": now,
                    "sync": sync_field,
                    "dry": True,
                },
            )
            return {
                "ok": True,
                "deduped": False,
                "dry": True,
                "sig": sig,
                "sync": sync_field,
            }
        post = filer_post or _post
        result = post(title, body, repo=repo, sig=sig)
        new_number = None
        if isinstance(result, dict):
            for key in ("number", "issue", "issue_number"):
                if result.get(key) is not None:
                    try:
                        new_number = int(result[key])
                        break
                    except (TypeError, ValueError):
                        pass
            nested = result.get("result")
            if new_number is None and isinstance(nested, dict):
                for key in ("number", "issue", "issue_number"):
                    if nested.get(key) is not None:
                        try:
                            new_number = int(nested[key])
                            break
                        except (TypeError, ValueError):
                            pass
        _save_state(
            mid,
            {
                "number": new_number,
                "sig": sig,
                "count": 1,
                "first_seen": now,
                "last_seen": now,
                "sync": sync_field,
                "result": result if isinstance(result, dict) else {"ok": True},
            },
        )
        return {
            "ok": True,
            "deduped": False,
            "number": new_number,
            "sig": sig,
            "sync": sync_field,
            "result": result,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def write_sync_status(
    *,
    behind: int,
    reason: str,
    machine: str | None = None,
    ok: bool = False,
    install_root: str | None = None,
) -> Path | None:
    """Write digest sync stamp (no secrets). Returns path written."""
    try:
        mid = machine_id(machine)
        sync_field = format_sync_field(behind, reason) if not ok else ""
        doc = {
            "machine": mid,
            "ok": bool(ok),
            "behind": max(0, int(behind) if behind is not None else 0),
            "reason": _sanitize_reason(reason) if not ok else "",
            "sync": sync_field,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        dirty_scripts = []
        try:
            import recycleseat as _rs

            blob = " ".join(
                str(x) for x in (reason, os.environ.get("BOB_SYNC_DIRTY_PATHS") or "")
            )
            dirty_scripts = _rs.dirty_recycle_script_paths(blob.replace(",", " ").split())
        except Exception:
            dirty_scripts = []
        if dirty_scripts:
            doc["recycle_scripts_dirty"] = dirty_scripts
            extra = "recycle-scripts-dirty:" + ",".join(dirty_scripts)
            if extra not in str(doc.get("sync") or ""):
                doc["sync"] = (str(doc.get("sync") or "").strip() + " " + extra).strip()
            if extra not in str(doc.get("reason") or ""):
                doc["reason"] = (str(doc.get("reason") or "").strip() + " " + extra).strip()
        override = (os.environ.get("BOB_SYNC_STATUS_DIR") or "").strip()
        paths: list[Path] = []
        if override:
            d = Path(override)
            d.mkdir(parents=True, exist_ok=True)
            paths.append(d / f"{mid}.json")
        if install_root:
            d = Path(install_root) / "logs"
            d.mkdir(parents=True, exist_ok=True)
            paths.append(d / "sync-status.json")
        if not paths:
            base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or ".")
            d = base / "Bobiverse" / "sync-status"
            d.mkdir(parents=True, exist_ok=True)
            paths.append(d / f"{mid}.json")
        last: Path | None = None
        for path in paths:
            path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
            last = path
        return last
    except Exception:
        return None


def read_sync_field(machine: str | None = None, install_root: str | None = None) -> str:
    """Best-effort sync string for digest merge payload."""
    mid = machine_id(machine)
    cands: list[Path] = []
    override = (os.environ.get("BOB_SYNC_STATUS_DIR") or "").strip()
    if override:
        cands.append(Path(override) / f"{mid}.json")
    if install_root:
        cands.append(Path(install_root) / "logs" / "sync-status.json")
    base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or ".")
    cands.append(base / "Bobiverse" / "sync-status" / f"{mid}.json")
    for path in cands:
        try:
            if not path.is_file():
                continue
            doc = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(doc, dict):
                continue
            if doc.get("ok"):
                return ""
            sync = str(doc.get("sync") or "").strip()
            if sync:
                return sync
            return format_sync_field(int(doc.get("behind") or 0), str(doc.get("reason") or ""))
        except Exception:
            continue
    return ""
