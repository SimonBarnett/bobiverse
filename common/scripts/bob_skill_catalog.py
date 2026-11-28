"""FR #10079: public Bob skill catalog (name, title, description, SKILL.md).

No tokens. A skill whose body contains a secret-shaped line is omitted.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_SECRET = re.compile(
    r"(password\s*=|github_pat_|ghp_[A-Za-z0-9]|BEGIN OPENSSH|AKIA[0-9A-Z]{16})",
    re.I,
)
# Docs name the hunter shapes inside markdown code. Those spans are not stored credentials.
_CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)


def prose_for_secret_scan(text: str) -> str:
    return _CODE.sub(" ", text or "")


def contains_secret(text: str) -> bool:
    return _SECRET.search(prose_for_secret_scan(text)) is not None
_FM = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = _FM.match(text)
    if not match:
        return {}, text
    meta: dict[str, str] = {}
    key = ""
    buf: list[str] = []
    for line in match.group(1).splitlines():
        if line.startswith("  ") and key:
            buf.append(line.strip())
            continue
        if buf and key:
            meta[key] = " ".join(buf).strip()
            buf = []
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        key = k.strip()
        val = v.strip()
        if val and val != ">" and val != "|":
            meta[key] = val.strip('"')
            key = ""
        else:
            buf = []
    if buf and key:
        meta[key] = " ".join(buf).strip()
    return meta, text[match.end() :]


def _title(meta: dict[str, str], body: str, folder: str) -> str:
    if meta.get("title"):
        return meta["title"]
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return meta.get("name") or folder


def skill_record(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    if contains_secret(text):
        return None
    meta, body = _frontmatter(text)
    name = (meta.get("name") or path.parent.name).strip()
    desc = (meta.get("description") or "").strip()
    if len(desc) > 240:
        desc = desc[:237] + "..."
    return {
        "name": name,
        "title": _title(meta, body, path.parent.name),
        "description": desc,
        "skillMd": text,
    }


def build_catalog(roots: list[Path]) -> dict:
    skills: list[dict] = []
    seen: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*/SKILL.md")):
            rec = skill_record(path)
            if rec is None or rec["name"] in seen:
                continue
            seen.add(rec["name"])
            skills.append({k: rec[k] for k in ("name", "title", "description")})
    skills.sort(key=lambda r: r["name"])
    return {
        "host": "https://bob.ntsa.uk",
        "skills": skills,
    }


def load_skill(roots: list[Path], name: str) -> dict | None:
    want = (name or "").strip()
    if not want or "/" in want or "\\" in want or ".." in want:
        return None
    for root in roots:
        path = root / want / "SKILL.md"
        if not path.is_file():
            continue
        rec = skill_record(path)
        if rec is None or rec["name"] != want:
            continue
        return rec
    return None


def catalog_json(roots: list[Path]) -> str:
    return json.dumps(build_catalog(roots), indent=2)
