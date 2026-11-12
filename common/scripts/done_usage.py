"""FR #6387: measure seat model + token usage and stamp DONE lines.

The worker (not the model) appends measured counters when it relays DONE.
Never fabricate a zero: missing sources become ``tokens=unknown``.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping, Optional

_DONE_RX = re.compile(r"(?i)^DONE\b")
_MODEL_RX = re.compile(r"(?i)\bmodel=([^\s]+)")
_TOKENS_UNKNOWN_RX = re.compile(r"(?i)\btokens=unknown\b")
_LEGACY_TOKENS_RX = re.compile(r"(?i)\btokens=(\d+)\b")
_TOKENS_IN_RX = re.compile(r"(?i)\btokens_in=(\d+)\b")
_TOKENS_OUT_RX = re.compile(r"(?i)\btokens_out=(\d+)\b")
_TOKENS_CACHED_RX = re.compile(r"(?i)\btokens_cached=(\d+)\b")
_ATTEMPT_RX = re.compile(r"(?i)\battempt=(\d+)\b")
_SOURCE_RX = re.compile(r"(?i)\bsource=([^\s]+)")
# Strip model-written counters when a measured stamp replaces them.
_STRIP_USAGE_RX = re.compile(
    r"(?i)\s*\b(?:model|tokens|tokens_in|tokens_out|tokens_cached|worker_build|attempt|source)=[^\s]+"
)


def _empty(*, unknown: bool = True) -> dict[str, Any]:
    return {
        "model": "",
        "tokens_in": None,
        "tokens_out": None,
        "tokens_cached": None,
        "legacy_tokens": None,
        "tokens_unknown": bool(unknown),
        "tokens_total": None,
        "attempt": 1,
        "source": "done",
    }


def _int_or_none(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _normalize_model(raw: Any, *, default_provider: str = "") -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    if "/" in s:
        return s
    if default_provider:
        return f"{default_provider}/{s}"
    return s


def parse_done_usage(rest: str) -> dict[str, Any]:
    """Parse measured / legacy token fields from the text after the DONE verb+job."""
    text = rest or ""
    out = _empty(unknown=False)
    m = _MODEL_RX.search(text)
    if m:
        out["model"] = str(m.group(1)).strip()
    tin = _TOKENS_IN_RX.search(text)
    tout = _TOKENS_OUT_RX.search(text)
    tc = _TOKENS_CACHED_RX.search(text)
    if tin:
        out["tokens_in"] = int(tin.group(1))
    if tout:
        out["tokens_out"] = int(tout.group(1))
    if tc:
        out["tokens_cached"] = int(tc.group(1))
    if _TOKENS_UNKNOWN_RX.search(text):
        out["tokens_unknown"] = True
        out["legacy_tokens"] = None
    else:
        leg = _LEGACY_TOKENS_RX.search(text)
        if leg:
            out["legacy_tokens"] = int(leg.group(1))
    measured = any(out[k] is not None for k in ("tokens_in", "tokens_out", "tokens_cached"))
    if measured:
        out["tokens_unknown"] = False
        total = 0
        for k in ("tokens_in", "tokens_out"):
            if out[k] is not None:
                total += int(out[k])
        out["tokens_total"] = total
    elif out["legacy_tokens"] is not None:
        out["tokens_unknown"] = False
        out["tokens_total"] = int(out["legacy_tokens"])
    else:
        out["tokens_unknown"] = True
        out["tokens_total"] = None
    am = _ATTEMPT_RX.search(text)
    out["attempt"] = int(am.group(1)) if am else 1
    sm = _SOURCE_RX.search(text)
    src = str(sm.group(1)).strip() if sm else "done"
    out["source"] = src or "done"
    return out


def format_done_usage_suffix(
    usage: Mapping[str, Any] | None,
    *,
    worker_build: str | None = None,
) -> str:
    """Wire suffix: measured fields, or ``tokens=unknown`` (never a fabricated 0).

    FR #6409: always ends with ``worker_build=<short|unknown>`` next to model/tokens.
    """
    u = dict(usage or {})
    model = str(u.get("model") or "").strip()
    tin = _int_or_none(u.get("tokens_in"))
    tout = _int_or_none(u.get("tokens_out"))
    tc = _int_or_none(u.get("tokens_cached"))
    unknown = bool(u.get("tokens_unknown"))
    measured = tin is not None or tout is not None or tc is not None
    parts: list[str] = []
    if model:
        parts.append(f"model={model}")
    if measured and not unknown:
        # Emit only fields the source actually provided (a real 0 is fine; a missing
        # field must not become a fabricated 0 on the wire).
        if tin is not None:
            parts.append(f"tokens_in={tin}")
        if tout is not None:
            parts.append(f"tokens_out={tout}")
        if tc is not None:
            parts.append(f"tokens_cached={tc}")
    else:
        parts.append("tokens=unknown")
    build = str(worker_build or "").strip() or "unknown"
    if build.lower() in ("", "none", "null"):
        build = "unknown"
    parts.append(f"worker_build={build}")
    # FR #6435: attempt/source distinguish retries from duplicate DONE writes.
    attempt = _int_or_none(u.get("attempt"))
    if attempt is not None and int(attempt) != 1:
        parts.append(f"attempt={int(attempt)}")
    source = str(u.get("source") or "").strip()
    if source and source.lower() not in ("", "done", "none", "null"):
        parts.append(f"source={source}")
    return " ".join(parts)


def _strip_usage_fields(text: str) -> str:
    return _STRIP_USAGE_RX.sub("", text or "").rstrip()


def enrich_done_payload(
    payload: str,
    usage: Mapping[str, Any] | None,
    *,
    worker_build: str | None = None,
) -> str:
    """Append a measured usage stamp to a DONE line; leave non-DONE lines alone.

    When a measured value exists, model-written ``tokens=`` / ``model=`` counters
    on the line are removed so the measured stamp wins.

    FR #6409: ``worker_build=<short|unknown>`` is always included.
    """
    text = (payload or "").strip()
    if not text or not _DONE_RX.match(text):
        return payload if payload is not None else ""
    cleaned = _strip_usage_fields(text).rstrip()
    suffix = format_done_usage_suffix(usage, worker_build=worker_build)
    if not suffix:
        return cleaned
    return f"{cleaned} {suffix}".rstrip()


def _cache_read_tokens(raw: Any) -> Optional[int]:
    """Cached-input tokens from an OpenCode ``cache`` shape (``{read, write}``) or a plain int."""
    if isinstance(raw, dict):
        return _int_or_none(raw.get("read"))
    return _int_or_none(raw)


def _from_token_map(
    raw: Mapping[str, Any],
    *,
    model: str = "",
    default_provider: str = "",
) -> dict[str, Any]:
    out = _empty(unknown=True)
    if model:
        out["model"] = _normalize_model(model, default_provider=default_provider)
    # Accept several common key shapes from agent CLIs / fixtures.
    tin = (
        _int_or_none(raw.get("tokens_in"))
        if "tokens_in" in raw
        else _int_or_none(raw.get("inputTokens"))
        if "inputTokens" in raw
        else _int_or_none(raw.get("input_tokens"))
        if "input_tokens" in raw
        else _int_or_none(raw.get("prompt_tokens"))
        if "prompt_tokens" in raw
        else _int_or_none(raw.get("input"))
        if "input" in raw
        else None
    )
    tout = (
        _int_or_none(raw.get("tokens_out"))
        if "tokens_out" in raw
        else _int_or_none(raw.get("outputTokens"))
        if "outputTokens" in raw
        else _int_or_none(raw.get("output_tokens"))
        if "output_tokens" in raw
        else _int_or_none(raw.get("completion_tokens"))
        if "completion_tokens" in raw
        else _int_or_none(raw.get("output"))
        if "output" in raw
        else None
    )
    tc = (
        _int_or_none(raw.get("tokens_cached"))
        if "tokens_cached" in raw
        else _int_or_none(raw.get("cachedReadTokens"))
        if "cachedReadTokens" in raw
        else _int_or_none(raw.get("cache_read_tokens"))
        if "cache_read_tokens" in raw
        else _int_or_none(raw.get("cache_read"))
        if "cache_read" in raw
        else _int_or_none(raw.get("cached_tokens"))
        if "cached_tokens" in raw
        else _cache_read_tokens(raw.get("cache"))
        if "cache" in raw
        else None
    )
    if tin is None and tout is None and tc is None:
        return out
    out["tokens_in"] = tin
    out["tokens_out"] = tout
    out["tokens_cached"] = tc
    out["tokens_unknown"] = False
    total = 0
    if tin is not None:
        total += tin
    if tout is not None:
        total += tout
    out["tokens_total"] = total
    return out


def _load_json(path: Path | str | None) -> Any:
    if path is None:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _grok_model_usage_map(doc: Mapping[str, Any], session: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return the ``modelUsage`` dict from session or document root, if present."""
    for container in (session, doc):
        raw = container.get("modelUsage")
        if isinstance(raw, dict):
            return raw
    return None


def _grok_counted_model_usage(model_usage: Mapping[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Entries with a non-empty model key and a dict body (FR #6781 counted rows)."""
    out: list[tuple[str, dict[str, Any]]] = []
    for key, entry in model_usage.items():
        mid = str(key or "").strip()
        if not mid or not isinstance(entry, dict):
            continue
        out.append((mid, entry))
    return out


def read_grok_usage(path: Path | str | None) -> dict[str, Any]:
    """Read ``~/.grok/sessions/.../<uuid>/usage.json`` (usage only; no auth files).

    FR #6781: when ``modelUsage`` has exactly one counted entry, that entry's
    model id and token fields win over a different ``primaryModelId`` / session
    totals. More than one counted entry stays ``tokens=unknown``.
    """
    doc = _load_json(path)
    if not isinstance(doc, dict):
        return _empty(unknown=True)
    session = doc.get("session") if isinstance(doc.get("session"), dict) else doc
    if not isinstance(session, dict):
        return _empty(unknown=True)
    model_usage = _grok_model_usage_map(doc, session)
    if model_usage is not None:
        counted = _grok_counted_model_usage(model_usage)
        if len(counted) > 1:
            return _empty(unknown=True)
        if len(counted) == 1:
            mid, entry = counted[0]
            return _from_token_map(entry, model=mid, default_provider="xai")
    model = (
        session.get("primaryModelId")
        or doc.get("primaryModelId")
        or doc.get("model")
        or ""
    )
    return _from_token_map(session, model=str(model), default_provider="xai")


_CURSOR_SECRET_NAMES = frozenset(
    {
        "identity.json",
        "auth.json",
        "github.token",
        ".password",
    }
)


def _cursor_usage_nonzero(usage: Mapping[str, Any] | None) -> bool:
    u = dict(usage or {})
    if bool(u.get("tokens_unknown")):
        return False
    for key in ("tokens_in", "tokens_out", "tokens_cached"):
        n = _int_or_none(u.get(key))
        if n is not None and int(n) != 0:
            return True
    return False


def _finalize_cursor_usage(usage: Mapping[str, Any] | None) -> dict[str, Any]:
    """FR #6782: zero or absent Cursor token fields become tokens=unknown (never tokens_in=0)."""
    u = dict(usage or {})
    if not _cursor_usage_nonzero(u):
        out = _empty(unknown=True)
        model = str(u.get("model") or "").strip()
        if model:
            out["model"] = model
        return out
    return u


def read_cursor_usage(path: Path | str | None) -> dict[str, Any]:
    """Read a Cursor agent usage/export JSON fixture (no secrets)."""
    doc = _load_json(path)
    if not isinstance(doc, dict):
        return _empty(unknown=True)
    model = doc.get("model") or doc.get("modelId") or doc.get("primaryModelId") or ""
    usage = doc.get("usage") if isinstance(doc.get("usage"), dict) else doc
    return _finalize_cursor_usage(
        _from_token_map(usage, model=str(model), default_provider="cursor")
    )


def _cursor_usage_from_obj(doc: Any) -> dict[str, Any]:
    if not isinstance(doc, dict):
        return _empty(unknown=True)
    model = doc.get("model") or doc.get("modelId") or doc.get("primaryModelId") or ""
    usage = doc.get("usage") if isinstance(doc.get("usage"), dict) else doc
    return _finalize_cursor_usage(
        _from_token_map(usage, model=str(model), default_provider="cursor")
    )


def _iter_cursor_chat_files(chat_dir: Path) -> list[Path]:
    out: list[Path] = []
    try:
        for p in sorted(chat_dir.iterdir(), key=lambda x: x.name.lower()):
            if not p.is_file():
                continue
            name = p.name.lower()
            if name in _CURSOR_SECRET_NAMES or name.endswith(".password"):
                continue
            if name.endswith((".json", ".jsonl")):
                out.append(p)
    except OSError:
        return []
    return out


def read_cursor_chat_dir(chat_dir: Path | str | None) -> dict[str, Any]:
    """FR #6782: live read of the bound Cursor chat dir when it has non-zero token fields."""
    if chat_dir is None:
        return _empty(unknown=True)
    root = Path(chat_dir)
    if not root.is_dir():
        return _empty(unknown=True)
    for preferred in ("cursor-usage.json", "usage.json"):
        cand = root / preferred
        if cand.is_file():
            u = read_cursor_usage(cand)
            if _cursor_usage_nonzero(u):
                return u
    for path in _iter_cursor_chat_files(root):
        if path.suffix.lower() == ".jsonl":
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        doc = json.loads(line)
                    except Exception:
                        continue
                    u = _cursor_usage_from_obj(doc)
                    if _cursor_usage_nonzero(u):
                        return u
            except OSError:
                continue
            continue
        u = read_cursor_usage(path)
        if _cursor_usage_nonzero(u):
            return u
    return _empty(unknown=True)


def read_opencode_usage(path: Path | str | None) -> dict[str, Any]:
    """Read an OpenCode session export / stats JSON fixture (no secrets)."""
    doc = _load_json(path)
    if not isinstance(doc, dict):
        return _empty(unknown=True)
    model = doc.get("model") or doc.get("modelId") or doc.get("primaryModelId") or ""
    tokens = doc.get("tokens") if isinstance(doc.get("tokens"), dict) else None
    if tokens is not None:
        return _from_token_map(tokens, model=str(model), default_provider="opencode")
    usage = doc.get("usage") if isinstance(doc.get("usage"), dict) else doc
    return _from_token_map(usage, model=str(model), default_provider="opencode")


def opencode_data_dir(env: Mapping[str, str] | None = None) -> Path:
    """OpenCode data directory: ``$XDG_DATA_HOME/opencode`` else ``~/.local/share/opencode``.

    FR #6420: OpenCode (v1.14+) stores its SQLite database here. ``auth.json``
    also lives here, but this helper only returns the directory; nothing reads auth.
    """
    env = dict(os.environ if env is None else env)
    custom = str(env.get("BOB_OPENCODE_DATA_DIR") or "").strip()
    if custom:
        return Path(custom)
    xdg = str(env.get("XDG_DATA_HOME") or "").strip()
    if xdg:
        return Path(xdg) / "opencode"
    return Path.home() / ".local" / "share" / "opencode"


def _opencode_model_from_json(raw: Any) -> str:
    """``providerID/id`` from an OpenCode session ``model`` JSON (or string)."""
    doc = raw
    if isinstance(doc, str):
        try:
            doc = json.loads(doc)
        except Exception:
            return str(doc or "").strip()
    if not isinstance(doc, dict):
        return ""
    mid = str(doc.get("id") or "").strip()
    prov = str(doc.get("providerID") or doc.get("provider") or "").strip()
    if not mid:
        return ""
    if "/" in mid:
        return mid
    if prov:
        return f"{prov}/{mid}"
    return mid


def _norm_oc_dir(path: str) -> str:
    """Normalize a directory for case/slash-insensitive OpenCode session matching."""
    raw = str(path or "").strip()
    if not raw:
        return ""
    try:
        return os.path.normcase(os.path.normpath(raw))
    except Exception:
        return raw.lower()


def _oc_dir_variants(path: str) -> set[str]:
    """Normalized forms of a job worktree path (raw + filesystem-resolved)."""
    raw = str(path or "").strip()
    if not raw:
        return set()
    out = {_norm_oc_dir(raw)}
    try:
        out.add(_norm_oc_dir(str(Path(raw).resolve())))
    except Exception:
        pass
    out.discard("")
    return out


def read_opencode_sqlite_usage(
    data_dir: Path | str | None = None,
    *,
    directory: str = "",
) -> dict[str, Any]:
    """Per-job OpenCode token totals from ``opencode.db`` (read-only, no secrets).

    FR #6420: sums the ``session`` aggregate token columns for every session whose
    ``directory`` matches *directory* (the job worktree). No matching session, a
    missing/unreadable db, or an all-empty result becomes ``tokens=unknown`` so the
    DONE line and ledger never carry invented numbers.
    """
    want = _oc_dir_variants(directory)
    if not want:
        return _empty(unknown=True)
    base = Path(data_dir) if data_dir is not None else opencode_data_dir()
    db = base / "opencode.db"
    if not db.is_file():
        return _empty(unknown=True)
    import sqlite3

    try:
        db_abs = db.resolve()
    except Exception:
        db_abs = db
    try:
        uri = db_abs.as_uri() + "?mode=ro"
    except ValueError:
        uri = f"file:{db_abs.as_posix()}?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True)
    except sqlite3.Error:
        return _empty(unknown=True)
    tin = 0
    tout = 0
    tc = 0
    model = ""
    matched = False
    try:
        try:
            rows = con.execute(
                "SELECT model, tokens_input, tokens_output, tokens_cache_read, directory "
                "FROM session"
            ).fetchall()
        except sqlite3.Error:
            return _empty(unknown=True)
        for model_raw, t_in, t_out, t_cr, sess_dir in rows:
            if _norm_oc_dir(str(sess_dir or "")) not in want:
                continue
            matched = True
            tin += int(t_in or 0)
            tout += int(t_out or 0)
            tc += int(t_cr or 0)
            if not model:
                model = _opencode_model_from_json(model_raw)
    finally:
        con.close()
    if not matched:
        return _empty(unknown=True)
    out = _empty(unknown=False)
    if model:
        out["model"] = model
    out["tokens_in"] = tin
    out["tokens_out"] = tout
    out["tokens_cached"] = tc
    out["tokens_unknown"] = False
    out["tokens_total"] = tin + tout
    return out


def read_aider_usage(path: Path | str | None) -> dict[str, Any]:
    """Read an Aider usage/cost JSON fixture (no secrets)."""
    doc = _load_json(path)
    if not isinstance(doc, dict):
        return _empty(unknown=True)
    model = doc.get("model") or doc.get("main_model") or ""
    return _from_token_map(doc, model=str(model), default_provider="aider")



def usage_delta(
    baseline: Mapping[str, Any] | None,
    current: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """FR #6435: per-job tokens = current cumulative minus baseline at job start.

    When either side is unknown/missing, return unknown (never invent a 0 spend).
    Negative deltas (counter reset) fall back to the current absolute reading.
    """
    cur = dict(current or {})
    base = dict(baseline or {})
    if cur.get("tokens_unknown") or (
        cur.get("tokens_in") is None
        and cur.get("tokens_out") is None
        and cur.get("tokens_cached") is None
        and cur.get("legacy_tokens") is None
    ):
        out = _empty(unknown=True)
        out["model"] = str(cur.get("model") or base.get("model") or "")
        return out
    if not base or base.get("tokens_unknown"):
        # No baseline: treat current as the job total (first job on a seat / fixture).
        out = dict(cur)
        out.setdefault("attempt", 1)
        out.setdefault("source", "done")
        return out

    def _delta(key: str) -> Optional[int]:
        c = _int_or_none(cur.get(key))
        b = _int_or_none(base.get(key))
        if c is None:
            return None
        if b is None:
            return c
        d = int(c) - int(b)
        return d if d >= 0 else c

    tin = _delta("tokens_in")
    tout = _delta("tokens_out")
    tc = _delta("tokens_cached")
    out = _empty(unknown=False)
    out["model"] = str(cur.get("model") or base.get("model") or "")
    out["tokens_in"] = tin
    out["tokens_out"] = tout
    out["tokens_cached"] = tc
    if tin is None and tout is None and tc is None:
        out["tokens_unknown"] = True
        out["tokens_total"] = None
    else:
        out["tokens_unknown"] = False
        total = 0
        if tin is not None:
            total += tin
        if tout is not None:
            total += tout
        out["tokens_total"] = total
    out["attempt"] = _int_or_none(cur.get("attempt")) or 1
    out["source"] = str(cur.get("source") or "done")
    return out


def load_usage_baseline(path: Path | str | None) -> dict[str, Any]:
    """Load a job-start usage snapshot written by the worker (FR #6435)."""
    doc = _load_json(path)
    if not isinstance(doc, dict):
        return _empty(unknown=True)
    usage = doc.get("usage") if isinstance(doc.get("usage"), dict) else doc
    if not isinstance(usage, dict):
        return _empty(unknown=True)
    out = _from_token_map(usage, model=str(usage.get("model") or doc.get("model") or ""))
    if out.get("tokens_unknown") and any(
        k in usage for k in ("tokens_in", "tokens_out", "tokens_cached", "inputTokens", "outputTokens")
    ):
        return _from_token_map(usage, model=str(usage.get("model") or ""))
    # Prefer already-normalized fields when present.
    if any(usage.get(k) is not None for k in ("tokens_in", "tokens_out", "tokens_cached")):
        out = _empty(unknown=False)
        out["model"] = str(usage.get("model") or doc.get("model") or "")
        out["tokens_in"] = _int_or_none(usage.get("tokens_in"))
        out["tokens_out"] = _int_or_none(usage.get("tokens_out"))
        out["tokens_cached"] = _int_or_none(usage.get("tokens_cached"))
        if out["tokens_in"] is None and out["tokens_out"] is None and out["tokens_cached"] is None:
            return _empty(unknown=True)
        out["tokens_unknown"] = False
        total = 0
        if out["tokens_in"] is not None:
            total += int(out["tokens_in"])
        if out["tokens_out"] is not None:
            total += int(out["tokens_out"])
        out["tokens_total"] = total
    return out


def save_usage_baseline(path: Path | str, usage: Mapping[str, Any] | None, *, job: str = "") -> None:
    """Persist a job-start usage snapshot next to the seat run dir (FR #6435)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    u = dict(usage or {})
    payload = {
        "job": str(job or ""),
        "usage": {
            "model": str(u.get("model") or ""),
            "tokens_in": u.get("tokens_in"),
            "tokens_out": u.get("tokens_out"),
            "tokens_cached": u.get("tokens_cached"),
            "tokens_unknown": bool(u.get("tokens_unknown", True)),
        },
    }
    p.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def measure_seat_usage(
    kind: str,
    *,
    grok_usage_path: Path | str | None = None,
    cursor_usage_path: Path | str | None = None,
    cursor_chat_dir: Path | str | None = None,
    opencode_usage_path: Path | str | None = None,
    aider_usage_path: Path | str | None = None,
) -> dict[str, Any]:
    """Dispatch to the agent-kind usage reader. Missing source → tokens=unknown."""
    k = (kind or "").strip().lower()
    if k == "grok":
        return read_grok_usage(grok_usage_path)
    if k in ("cursor", "cursor-agent", "agent"):
        fixture = Path(cursor_usage_path) if cursor_usage_path else None
        if fixture is not None and fixture.is_file():
            return read_cursor_usage(fixture)
        live = read_cursor_chat_dir(cursor_chat_dir)
        if _cursor_usage_nonzero(live):
            return live
        if fixture is not None:
            return read_cursor_usage(fixture)
        return live if live else _empty(unknown=True)
    if k in ("opencode", "oc"):
        return read_opencode_usage(opencode_usage_path)
    if k == "aider":
        return read_aider_usage(aider_usage_path)
    return _empty(unknown=True)


def grok_usage_path_for_session(
    cwd: str,
    session_id: str,
    sessions_root: Path | str | None = None,
) -> Optional[Path]:
    """Resolve ``usage.json`` beside the grok session ``events.jsonl``."""
    from urllib.parse import quote

    if not session_id or not re.fullmatch(r"[0-9a-fA-F-]{36}", str(session_id)):
        return None
    root = Path(sessions_root) if sessions_root else Path.home() / ".grok" / "sessions"
    for key in (quote(str(cwd), safe=""), quote(str(cwd).rstrip("\\"), safe="")):
        d = root / key / str(session_id)
        if d.is_dir():
            return d / "usage.json"
    return None
