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
from typing import Any, Iterable

BUILDS_CATALOG_NAME = "builds-catalog.json"
BUILDS_PATH = "/bob/v1/builds"
DEFAULT_BUILDS_URL = "https://irc.ntsa.uk/bob/v1/builds"
BUILDS_URL_ENV = "BOB_BUILDS_URL"

# owner/repo or owner/repo:relative/path
_YML_RE = re.compile(
    r"^(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(?::(?P<path>.+))?$"
)
_NUMERIC_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:\.\d+)?$")
_MACHINE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
DEFAULT_RECIPE_REL = ".bobiverse/build.yml"


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


def parse_yml_field(yml: str) -> tuple[str, str]:
    """Return ``(owner/repo, relative_recipe_path)``."""
    text = (yml or "").strip()
    m = _YML_RE.match(text)
    if not m:
        raise ValueError(f"bad yml field: {yml!r}")
    repo = m.group("repo")
    rel = (m.group("path") or "").strip().lstrip("/\\") or DEFAULT_RECIPE_REL
    rel = rel.replace("\\", "/")
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


def format_catalog_lines(entries: Iterable[BuildCatalogEntry]) -> list[str]:
    rows = list(entries)
    if not rows:
        return [
            "build: catalog empty (edit builds-catalog.json on chair home)",
        ]
    lines = ["build catalog:"]
    for i, e in enumerate(rows, 1):
        dep = ",".join(e.dep) if e.dep else "-"
        ver = e.version or "(set on !build n)"
        ref = e.ref or "HEAD"
        lines.append(
            f"  {i}) {e.name}  yml={e.yml}  install={e.install}  "
            f"dep={dep}  version={ver}  ref={ref}  output={e.output}"
        )
    lines.append(
        "build: !build n [version] [ref]  |  !build dry-run n  |  "
        "!build status n  |  !build cancel n"
    )
    return lines


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
