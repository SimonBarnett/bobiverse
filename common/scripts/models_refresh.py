"""FR #8820 / FR #9266: POST /bob/v1/models/refresh — rebuild per-CLI models catalog.

Listing sources (no scraping, no cloud API keys):
  - Grok: ``grok models`` (https://docs.x.ai/docs/cli)
  - Cursor: ``agent models`` (Cursor agent CLI)
  - OpenCode: ``opencode models`` (https://opencode.ai)

FR #9266 / BOB-TRAY-UI-06: Weights client may POST a discovered catalog instead of
chair-side CLI spawn::

  ``{"source":"weights-client","clis":{"grok":["id",...],"cursor":[...],"opencode":[...]}}``

``clis`` values may also be ``[{"model":"id",...}, ...]``. Chair listing (empty body
or ``{"clis":["grok",...]}``) remains for ops; fleet seats own discovery.

A failed or empty listing leaves that CLI's store entry untouched. Agent
selections are never rewritten; GET marks absent models ``stale: true``.
Per-CLI in-memory rate limit: one attempt per 60 s (restart resets).
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import models_catalog as mc

log = logging.getLogger("models_refresh")

MODELS_REFRESH_PATH = "/bob/v1/models/refresh"
REFRESH_CLIS: tuple[str, ...] = ("grok", "cursor", "opencode")
RATE_WINDOW_S = 60.0
LISTING_TIMEOUT_S = 20.0
LISTING_STDOUT_CAP = 256 * 1024
CHAIR_BODY_LIMIT = 4096
CLIENT_CATALOG_BODY_LIMIT = 256 * 1024
CLIENT_SOURCE = "weights-client"

REASON_NOT_INSTALLED = "not_installed"
REASON_TIMEOUT = "timeout"
REASON_EXIT_NONZERO = "exit_nonzero"
REASON_SPAWN_ERROR = "spawn_error"
REASON_EMPTY_LISTING = "empty_listing"

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_GROK_BULLET_RE = re.compile(r"^[\*\-\u2022]\s+")
_HEADER_RE = re.compile(
    r"^(available models|models|default model|you are logged|logged in)\b",
    re.IGNORECASE,
)


class ListingError(Exception):
    """Raised by a lister with a fixed reason code."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


ListerFn = Callable[[], list[str]]
ClockFn = Callable[[], float]


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text or "")


def parse_grok_models_text(text: str | None) -> list[str]:
    """Leading model-ID token per line; strip `` - …`` suffixes and ``(current)``."""
    if not text:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in strip_ansi(text).splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if _HEADER_RE.match(line):
            continue
        if line.lower().startswith("default model:"):
            continue
        line = _GROK_BULLET_RE.sub("", line).strip()
        if not line:
            continue
        # Drop trailing markers like "(default)" / "(current)".
        line = re.sub(r"\s*\([^)]*\)\s*$", "", line).strip()
        if " - " in line:
            line = line.split(" - ", 1)[0].strip()
        token = line.split()[0] if line.split() else ""
        token = token.strip().strip("*")
        if not token or "/" in token and token.count("/") > 1:
            # Grok ids are plain tokens; skip odd noise.
            if not re.match(r"^[\w.\-]+$", token or ""):
                continue
        if not re.match(r"^[\w.\-]+$", token):
            continue
        if token.lower() in {"available", "models", "model", "default"}:
            continue
        if token not in seen:
            seen.add(token)
            out.append(token)
    return out


def parse_cursor_models_text(text: str | None) -> list[str]:
    """Same leading-token rules as Grok (Cursor ``agent models`` listing)."""
    return parse_grok_models_text(text)


def parse_opencode_models_text(text: str | None) -> list[str]:
    """Keep full ``provider/model`` lines; dedupe; retain order."""
    if not text:
        return []
    out: list[str] = []
    seen: set[str] = set()
    model_line_re = re.compile(r"^[\w.\-]+/[\w.\-:]+$")
    for raw in strip_ansi(text).splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if " - " in line:
            line = line.split(" - ", 1)[0].strip()
        line = re.sub(r"\s*\([^)]*\)\s*$", "", line).strip()
        if not model_line_re.match(line):
            continue
        if line not in seen:
            seen.add(line)
            out.append(line)
    return out


def _which(name: str) -> str | None:
    from shutil import which

    return which(name)


def resolve_grok_exe(env: dict[str, str] | None = None) -> str | None:
    e = os.environ if env is None else env
    explicit = (e.get("BOB_GROK_EXE") or "").strip()
    if explicit and Path(explicit).is_file():
        return explicit
    found = _which("grok")
    if found:
        return found
    home = e.get("USERPROFILE") or e.get("HOME") or ""
    if home:
        candidate = Path(home) / ".grok" / "bin" / "grok.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def resolve_cursor_agent(env: dict[str, str] | None = None) -> str | None:
    """Prefer agent.cmd / cursor-agent.cmd — never agent.exe (collides with Grok)."""
    e = os.environ if env is None else env
    local = e.get("LOCALAPPDATA") or ""
    if local:
        candidate = Path(local) / "cursor-agent" / "agent.cmd"
        if candidate.is_file():
            return str(candidate)
    for name in ("agent.cmd", "cursor-agent.cmd", "agent", "cursor-agent"):
        found = _which(name)
        if found and not found.lower().endswith("agent.exe"):
            # Avoid grok's agent.exe when PATH has a bare `agent`.
            base = Path(found).name.lower()
            if base == "agent.exe":
                continue
            return found
    return None


def resolve_opencode_exe(env: dict[str, str] | None = None) -> str | None:
    e = os.environ if env is None else env
    explicit = (e.get("BOB_OPENCODE_EXE") or "").strip()
    if explicit and Path(explicit).is_file():
        return explicit
    return _which("opencode")


def _run_listing(
    argv: list[str],
    *,
    cwd: Path | str | None,
    env_extra: dict[str, str] | None = None,
    timeout_s: float = LISTING_TIMEOUT_S,
) -> str:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    flags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    try:
        proc = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=str(cwd) if cwd else None,
            env=env,
            timeout=timeout_s,
            check=False,
            creationflags=flags,
        )
    except FileNotFoundError as exc:
        raise ListingError(REASON_NOT_INSTALLED) from exc
    except subprocess.TimeoutExpired as exc:
        raise ListingError(REASON_TIMEOUT) from exc
    except OSError as exc:
        raise ListingError(REASON_SPAWN_ERROR) from exc
    if proc.returncode != 0:
        raise ListingError(REASON_EXIT_NONZERO)
    raw = proc.stdout or b""
    if len(raw) > LISTING_STDOUT_CAP:
        raw = raw[:LISTING_STDOUT_CAP]
    try:
        return raw.decode("utf-8", errors="replace")
    except Exception as exc:
        raise ListingError(REASON_SPAWN_ERROR) from exc


def list_grok_models(home: Path | str | None = None, env: dict[str, str] | None = None) -> list[str]:
    exe = resolve_grok_exe(env)
    if not exe:
        raise ListingError(REASON_NOT_INSTALLED)
    text = _run_listing(
        [exe, "models"],
        cwd=home,
        env_extra={"GROK_DISABLE_AUTOUPDATER": "1"},
    )
    ids = parse_grok_models_text(text)
    if not ids:
        raise ListingError(REASON_EMPTY_LISTING)
    return ids


def list_cursor_models(home: Path | str | None = None, env: dict[str, str] | None = None) -> list[str]:
    exe = resolve_cursor_agent(env)
    if not exe:
        raise ListingError(REASON_NOT_INSTALLED)
    text = _run_listing([exe, "models"], cwd=home)
    ids = parse_cursor_models_text(text)
    if not ids:
        raise ListingError(REASON_EMPTY_LISTING)
    return ids


def list_opencode_models(home: Path | str | None = None, env: dict[str, str] | None = None) -> list[str]:
    exe = resolve_opencode_exe(env)
    if not exe:
        raise ListingError(REASON_NOT_INSTALLED)
    text = _run_listing([exe, "models"], cwd=home)
    ids = parse_opencode_models_text(text)
    if not ids:
        raise ListingError(REASON_EMPTY_LISTING)
    return ids


def default_listers(home: Path | str) -> dict[str, ListerFn]:
    h = Path(home)

    def _g() -> list[str]:
        return list_grok_models(h)

    def _c() -> list[str]:
        return list_cursor_models(h)

    def _o() -> list[str]:
        return list_opencode_models(h)

    return {"grok": _g, "cursor": _c, "opencode": _o}


def _utc_iso(now: float | None = None) -> str:
    ts = time.time() if now is None else float(now)
    return (
        datetime.fromtimestamp(ts, tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def merge_cli_models(
    existing: dict[str, Any] | None,
    model_ids: Iterable[str],
    *,
    refreshed_at: str,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Replace models list; keep existing rows verbatim when id still listed.

    New ids get empty contexts/efforts. Returns ``(entry, added, removed)``.
    """
    prev_rows: list[dict[str, Any]] = []
    if isinstance(existing, dict):
        raw = existing.get("models")
        if isinstance(raw, list):
            prev_rows = [r for r in raw if isinstance(r, dict)]
    by_id: dict[str, dict[str, Any]] = {}
    for row in prev_rows:
        mid = str(row.get("model") or "").strip()
        if mid and mid not in by_id:
            by_id[mid] = row
    new_ids = [str(x).strip() for x in model_ids if str(x).strip()]
    new_set = set(new_ids)
    old_set = set(by_id)
    added = sorted(new_set - old_set)
    removed = sorted(old_set - new_set)
    models: list[dict[str, Any]] = []
    for mid in new_ids:
        if mid in by_id:
            models.append(by_id[mid])
        else:
            models.append({"model": mid, "contexts": [], "efforts": []})
    return {"models": models, "refreshed_at": refreshed_at}, added, removed


class ModelsRefreshController:
    """Rate-limit + list + merge. Tests inject ``listers`` and ``clock``."""

    def __init__(
        self,
        home: Path | str,
        *,
        listers: dict[str, ListerFn] | None = None,
        clock: ClockFn | None = None,
        rate_window_s: float = RATE_WINDOW_S,
    ) -> None:
        self.home = Path(home)
        self.listers = listers if listers is not None else default_listers(self.home)
        self.clock: ClockFn = clock or time.monotonic
        self.rate_window_s = float(rate_window_s)
        self._rate_lock = threading.Lock()
        self._last_attempt: dict[str, float] = {}

    def _reserve(self, clis: list[str]) -> tuple[bool, int]:
        """Atomically reserve all CLIs. Returns (ok, retry_after_s)."""
        now = self.clock()
        with self._rate_lock:
            blocked_for = 0.0
            for cli in clis:
                last = self._last_attempt.get(cli)
                if last is None:
                    continue
                remaining = self.rate_window_s - (now - last)
                if remaining > blocked_for:
                    blocked_for = remaining
            if blocked_for > 0:
                return False, max(1, int(blocked_for + 0.999))
            for cli in clis:
                self._last_attempt[cli] = now
            return True, 0

    def handle(
        self,
        body: bytes | str | None = None,
    ) -> tuple[int, bytes]:
        requested, client_catalog, err = _parse_refresh_request(body)
        if err is not None:
            return err
        assert requested is not None
        ok, retry_after = self._reserve(requested)
        if not ok:
            payload = {
                "error": "rate_limited",
                "retry_after_s": retry_after,
            }
            return 429, _json_bytes(payload)

        results: dict[str, Any] = {}
        successful: dict[str, list[str]] = {}
        if client_catalog is not None:
            # FR #9266: merge client-discovered ids; never spawn CLIs on the chair.
            for cli in requested:
                ids = client_catalog.get(cli) or []
                if not ids:
                    results[cli] = {
                        "status": "failed",
                        "reason": REASON_EMPTY_LISTING,
                        "refreshed_at": None,
                    }
                    continue
                successful[cli] = list(ids)
        else:
            for cli in requested:
                lister = self.listers.get(cli)
                if lister is None:
                    results[cli] = {
                        "status": "failed",
                        "reason": REASON_NOT_INSTALLED,
                        "refreshed_at": None,
                    }
                    continue
                try:
                    ids = list(lister())
                    if not ids:
                        raise ListingError(REASON_EMPTY_LISTING)
                    successful[cli] = ids
                except ListingError as exc:
                    results[cli] = {
                        "status": "failed",
                        "reason": exc.reason,
                        "refreshed_at": None,
                    }
                except Exception:
                    results[cli] = {
                        "status": "failed",
                        "reason": REASON_SPAWN_ERROR,
                        "refreshed_at": None,
                    }

        refreshed_at = _utc_iso(time.time())

        def _mutate(doc: dict[str, Any]) -> None:
            clis = doc.setdefault("clis", {})
            if not isinstance(clis, dict):
                clis = {}
                doc["clis"] = clis
            for cli, ids in successful.items():
                existing = clis.get(cli) if isinstance(clis.get(cli), dict) else None
                entry, added, removed = merge_cli_models(
                    existing, ids, refreshed_at=refreshed_at
                )
                clis[cli] = entry
                results[cli] = {
                    "status": "refreshed",
                    "refreshed_at": refreshed_at,
                    "added": added,
                    "removed": removed,
                }
                log.info(
                    "models_refresh cli=%s status=refreshed added=%d removed=%d source=%s",
                    cli,
                    len(added),
                    len(removed),
                    "weights-client" if client_catalog is not None else "chair",
                )
            if "copilot" not in successful:
                seed_copilot_on_refresh(clis, refreshed_at)
                results["copilot"] = {
                    "status": "seeded",
                    "refreshed_at": refreshed_at,
                    "added": list(COPILOT_REFRESH_SEED),
                    "removed": [],
                }
            for cli, info in results.items():
                if info.get("status") == "failed":
                    prev = clis.get(cli) if isinstance(clis.get(cli), dict) else None
                    prev_at = None
                    if isinstance(prev, dict):
                        prev_at = prev.get("refreshed_at")
                    info["refreshed_at"] = prev_at
                    log.info(
                        "models_refresh cli=%s status=failed reason=%s",
                        cli,
                        info.get("reason"),
                    )

        try:
            doc = mc.mutate_catalog_document(self.home, _mutate)
        except mc.CatalogUnavailable:
            return 503, _json_bytes({"error": "catalog_unavailable"})
        except mc.ModelsCatalogBusy:
            return 503, _json_bytes({"error": "busy"})
        except OSError:
            return 503, _json_bytes({"error": "catalog_unavailable"})

        clis_public = mc.clis_public_from_document(doc)
        out: dict[str, Any] = {"clis": clis_public, "refresh": results}
        if client_catalog is not None:
            out["source"] = CLIENT_SOURCE
        return 200, _json_bytes(out)


def _model_ids_from_client_entry(value: Any) -> list[str] | None:
    """Accept ``[\"id\", ...]`` or ``[{\"model\":\"id\"}, ...]``. None = bad shape."""
    if not isinstance(value, list):
        return None
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        mid = ""
        if isinstance(item, str):
            mid = item.strip()
        elif isinstance(item, dict):
            mid = str(item.get("model") or "").strip()
        else:
            return None
        if not mid:
            continue
        if mid not in seen:
            seen.add(mid)
            out.append(mid)
    return out


def _parse_refresh_request(
    body: bytes | str | None,
) -> tuple[list[str] | None, dict[str, list[str]] | None, tuple[int, bytes] | None]:
    """Return ``(cli_names, client_catalog_or_None, error_or_None)``."""
    if body is None or body == b"" or body == "":
        return list(REFRESH_CLIS), None, None
    raw = body if isinstance(body, (bytes, bytearray)) else str(body).encode("utf-8")
    # Peek for client catalog so we can allow a larger body.
    peek_limit = CLIENT_CATALOG_BODY_LIMIT
    if len(raw) > peek_limit:
        return None, None, (400, _json_bytes({"error": "bad_json"}))
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        return None, None, (400, _json_bytes({"error": "bad_json"}))
    if not text.strip():
        return list(REFRESH_CLIS), None, None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None, None, (400, _json_bytes({"error": "bad_json"}))
    if not isinstance(payload, dict):
        return None, None, (400, _json_bytes({"error": "bad_json"}))

    items = payload.get("clis") if "clis" in payload else None
    # FR #9266: dict ``clis`` = client-supplied catalog (Weights Refresh).
    if isinstance(items, dict):
        allowed_keys = {"clis", "source"}
        if set(payload.keys()) - allowed_keys:
            return None, None, (400, _json_bytes({"error": "bad_json"}))
        source = str(payload.get("source") or "").strip().lower()
        if source and source != CLIENT_SOURCE:
            return None, None, (400, _json_bytes({"error": "bad_json"}))
        if not items:
            return None, None, (400, _json_bytes({"error": "bad_json"}))
        catalog: dict[str, list[str]] = {}
        order: list[str] = []
        for raw_cli, raw_models in items.items():
            cli = str(raw_cli or "").strip().lower()
            if cli not in REFRESH_CLIS:
                return None, None, (
                    400,
                    _json_bytes({"error": "unknown_cli", "cli": cli}),
                )
            ids = _model_ids_from_client_entry(raw_models)
            if ids is None:
                return None, None, (400, _json_bytes({"error": "bad_json"}))
            if cli not in catalog:
                order.append(cli)
            catalog[cli] = ids
        return order, catalog, None

    # Chair listing path: empty body keys or ``{"clis":["grok",...]}``.
    if len(raw) > CHAIR_BODY_LIMIT:
        return None, None, (400, _json_bytes({"error": "bad_json"}))
    if set(payload.keys()) - {"clis"}:
        return None, None, (400, _json_bytes({"error": "bad_json"}))
    if "clis" not in payload:
        return list(REFRESH_CLIS), None, None
    if not isinstance(items, list) or not items:
        return None, None, (400, _json_bytes({"error": "bad_json"}))
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        cli = str(item or "").strip().lower()
        if cli not in REFRESH_CLIS:
            return None, None, (
                400,
                _json_bytes({"error": "unknown_cli", "cli": cli}),
            )
        if cli not in seen:
            seen.add(cli)
            out.append(cli)
    return out, None, None


def _parse_request_clis(body: bytes | str | None) -> tuple[list[str], tuple[int, bytes] | None]:
    """Back-compat wrapper: chair listing names only (ignores client catalog)."""
    requested, _catalog, err = _parse_refresh_request(body)
    if err is not None:
        return [], err
    return list(requested or []), None


def _json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


COPILOT_REFRESH_SEED = ("claude-haiku-4.5",)


def seed_copilot_on_refresh(clis: dict, refreshed_at: str) -> str:
    """FR #9994: merge a maintained Copilot catalog even when the client omits it."""
    existing = clis.get("copilot") if isinstance(clis.get("copilot"), dict) else None
    entry, _added, _removed = merge_cli_models(existing, list(COPILOT_REFRESH_SEED), refreshed_at=refreshed_at)
    clis["copilot"] = entry
    return "seeded"


def handle_models_refresh(
    body: bytes | str | None,
    home: Path | str,
    *,
    controller: ModelsRefreshController | None = None,
) -> tuple[int, bytes]:
    ctl = controller or ModelsRefreshController(home)
    return ctl.handle(body)
