"""FR #8490: buildable catalog for !build (GET /bob/v1/builds + chair list).

Static JSON on digest/chair home (``builds-catalog.json``). Webhook serves the
validated array. ``dep`` is documentation only.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

BUILDS_CATALOG_NAME = "builds-catalog.json"
BUILDS_PATH = "/bob/v1/builds"
DEFAULT_BUILDS_URL = "https://bob.ntsa.uk/bob/v1/builds"
BUILDS_URL_ENV = "BOB_BUILDS_URL"

# owner/repo or owner/repo:relative/path
_YML_RE = re.compile(
    r"^(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(?::(?P<path>.+))?$"
)
_NUMERIC_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:\.\d+)?$")
_MACHINE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
DEFAULT_RECIPE_REL = ".bobiverse/build.yml"

# FR #8770: single source of truth for !build usage (chair help, list footer, decide_build).
BUILD_USAGE_LINES = (
    "build: !build | !build <n> [version] [ref] | !build tests-only|dry-run <n> [version] [ref]",
    "build: !build preflight|status|cancel <n> | !build status | !build help  (version default: next patch)",
)

_IRC_ROW_MAX_BYTES = 400


@dataclass
class BuildCatalogEntry:
    name: str
    yml: str
    output: str
    install: str
    dep: list[str] = field(default_factory=list)
    version: str = ""
    ref: str = ""

    @property
    def repo(self) -> str:
        repo, _ = parse_yml_field(self.yml)
        return repo

    @property
    def recipe_rel(self) -> str:
        _, rel = parse_yml_field(self.yml)
        return rel


def default_builds_url() -> str:
    raw = (os.environ.get(BUILDS_URL_ENV) or "").strip()
    return raw or DEFAULT_BUILDS_URL


def catalog_path(home: Path | str) -> Path:
    return Path(home) / BUILDS_CATALOG_NAME


def _validate_recipe_rel(rel: str) -> str:
    """Normalize and refuse unsafe relative recipe paths (FR #8770)."""
    text = (rel or "").strip().replace("\\", "/")
    text = text.lstrip("/")
    if not text:
        return DEFAULT_RECIPE_REL
    if text.startswith("/") or text.startswith("\\"):
        raise ValueError(f"bad yml path (absolute): {rel!r}")
    if re.match(r"^[A-Za-z]:", text) or text.startswith("//"):
        raise ValueError(f"bad yml path (drive/UNC): {rel!r}")
    if any(ch in text for ch in "?#% \t\r\n"):
        raise ValueError(f"bad yml path (special/whitespace): {rel!r}")
    parts = text.split("/")
    if any(p == "" or p == "." or p == ".." for p in parts):
        raise ValueError(f"bad yml path (empty/dot segment): {rel!r}")
    return text


def parse_yml_field(yml: str) -> tuple[str, str]:
    """Return ``(owner/repo, relative_recipe_path)``."""
    text = (yml or "").strip()
    m = _YML_RE.match(text)
    if not m:
        raise ValueError(f"bad yml field: {yml!r}")
    repo = m.group("repo")
    raw_path = (m.group("path") or "").strip()
    if not raw_path:
        return repo, DEFAULT_RECIPE_REL
    rel = _validate_recipe_rel(raw_path)
    return repo, rel


def validate_entry(obj: Any) -> tuple[BuildCatalogEntry | None, str]:
    """Return ``(entry, \"\")`` or ``(None, reason)``."""
    if not isinstance(obj, dict):
        return None, "not an object"
    name = str(obj.get("name") or "").strip()
    yml = str(obj.get("yml") or "").strip()
    output = str(obj.get("output") or "").strip()
    install = str(obj.get("install") or "").strip().lower()
    if not name:
        return None, "missing name"
    if not yml:
        return None, "missing yml"
    if not output:
        return None, "missing output"
    if " " in output or "\t" in output:
        return None, "output must not contain whitespace (BUILD route token)"
    if not install:
        return None, "missing install"
    if install != "fleet" and not _MACHINE_RE.match(install):
        return None, f"bad install: {install!r}"
    try:
        parse_yml_field(yml)
    except ValueError as exc:
        return None, str(exc)
    dep_raw = obj.get("dep") if "dep" in obj else obj.get("deps")
    deps: list[str] = []
    if dep_raw is None:
        deps = []
    elif isinstance(dep_raw, list):
        deps = [str(x).strip() for x in dep_raw if str(x).strip()]
    else:
        return None, "dep must be a list"
    version = str(obj.get("version") or "").strip()
    if version and not _NUMERIC_VERSION_RE.match(version):
        return None, f"bad version: {version!r}"
    ref = str(obj.get("ref") or "").strip()
    return (
        BuildCatalogEntry(
            name=name,
            yml=yml,
            output=output,
            install=install,
            dep=deps,
            version=version,
            ref=ref,
        ),
        "",
    )


def load_catalog_file(home: Path | str) -> list[BuildCatalogEntry]:
    path = catalog_path(home)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []
    out: list[BuildCatalogEntry] = []
    for item in raw:
        entry, _why = validate_entry(item)
        if entry is not None:
            out.append(entry)
    return out


def catalog_to_public_list(entries: Iterable[BuildCatalogEntry]) -> list[dict]:
    rows: list[dict] = []
    for e in entries:
        rows.append(
            {
                "name": e.name,
                "yml": e.yml,
                "output": e.output,
                "install": e.install,
                "dep": list(e.dep),
                "version": e.version,
                "ref": e.ref,
            }
        )
    return rows


def catalog_to_json(entries: Iterable[BuildCatalogEntry]) -> bytes:
    return json.dumps(
        catalog_to_public_list(entries),
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _clip_utf8(text: str, max_bytes: int) -> str:
    """Clip *text* to ``max_bytes`` UTF-8 without splitting a codepoint."""
    raw = text or ""
    b = raw.encode("utf-8")
    if len(b) <= max_bytes:
        return raw
    cut = b[:max_bytes]
    while cut:
        try:
            return cut.decode("utf-8")
        except UnicodeDecodeError:
            cut = cut[:-1]
    return ""


def format_catalog_lines(
    entries: Iterable[BuildCatalogEntry],
    *,
    next_versions: dict | None = None,
    footer: Iterable[str] | None = None,
) -> list[str]:
    """IRC list rows: name/repo/install/version/ref only; each row ≤ 400 UTF-8 bytes.

    FR #8770: ``yml``/``dep``/``output`` stay in dry-run, not list rows.
    ``next_versions`` maps repo → display without the ``next:`` prefix (``2.0.2``,
    ``-``, ``?``). Blank entry.version → ``version=next:Y``.
    """
    rows = list(entries)
    if not rows:
        return [
            "build: catalog empty (edit builds-catalog.json on chair home)",
        ]
    nv = next_versions or {}
    lines = ["build catalog:"]
    for i, e in enumerate(rows, 1):
        repo = e.repo
        ref = (e.ref or "HEAD").strip() or "HEAD"
        if (e.version or "").strip():
            ver_disp = e.version.strip()
        else:
            preview = nv.get(repo, nv.get(repo.lower(), "?"))
            ver_disp = f"next:{preview}"
        # Clip name/ref so the full row stays ≤ 400 bytes.
        name = e.name
        for _ in range(8):
            row = (
                f"  {i}) {name}  {repo}  install={e.install}  "
                f"version={ver_disp}  ref={ref}"
            )
            if len(row.encode("utf-8")) <= _IRC_ROW_MAX_BYTES:
                break
            # Prefer shrinking name, then ref.
            overhead = len(row.encode("utf-8")) - _IRC_ROW_MAX_BYTES
            if len(name.encode("utf-8")) > 8:
                name = _clip_utf8(name, max(4, len(name.encode("utf-8")) - overhead - 1))
            elif len(ref.encode("utf-8")) > 4:
                ref = _clip_utf8(ref, max(3, len(ref.encode("utf-8")) - overhead - 1))
            else:
                row = _clip_utf8(row, _IRC_ROW_MAX_BYTES)
                break
        else:
            row = _clip_utf8(
                f"  {i}) {name}  {repo}  install={e.install}  "
                f"version={ver_disp}  ref={ref}",
                _IRC_ROW_MAX_BYTES,
            )
        lines.append(row)
    foot = list(footer) if footer is not None else list(BUILD_USAGE_LINES)
    lines.extend(foot)
    return lines


def load_catalog_entries_local_first(
    homes: Iterable[Path | str],
    *,
    http_fetcher: Callable | None = None,
) -> list[BuildCatalogEntry]:
    """FR #8770: digest/chair local files first; HTTP only when every home is empty."""
    for home in homes:
        try:
            rows = load_catalog_file(home)
        except Exception:
            rows = []
        if rows:
            return rows
    if http_fetcher is None:
        return []
    try:
        return list(http_fetcher() or [])
    except Exception:
        return []


def entry_at(entries: Iterable[BuildCatalogEntry], n: int) -> BuildCatalogEntry | None:
    rows = list(entries)
    if n < 1 or n > len(rows):
        return None
    return rows[n - 1]


def expand_install_targets(
    install: str,
    roster_machines: Iterable[str],
) -> list[str]:
    inst = (install or "").strip().lower()
    if inst == "fleet":
        seen: set[str] = set()
        out: list[str] = []
        for m in roster_machines:
            mid = str(m or "").strip().lower()
            if not mid or mid in seen:
                continue
            seen.add(mid)
            out.append(mid)
        return sorted(out)
    if inst:
        return [inst]
    return []


def fetch_catalog_http(
    url: str = "",
    *,
    timeout: float = 8.0,
) -> list[BuildCatalogEntry]:
    """GET catalog JSON array. Returns [] on any transport/parse failure."""
    target = (url or default_builds_url()).strip()
    if not target:
        return []
    try:
        req = urllib.request.Request(
            target,
            headers={"Accept": "application/json", "User-Agent": "bobiverse-builds-catalog"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        data = json.loads(raw.decode("utf-8"))
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
        OSError,
        UnicodeError,
        ValueError,
    ):
        return []
    if not isinstance(data, list):
        return []
    out: list[BuildCatalogEntry] = []
    for item in data:
        entry, _why = validate_entry(item)
        if entry is not None:
            out.append(entry)
    return out


def handle_builds_get(home: Path | str) -> tuple[int, bytes]:
    """BobCallback GET /bob/v1/builds → validated catalog JSON."""
    entries = load_catalog_file(home)
    body = catalog_to_json(entries)
    return 200, body
