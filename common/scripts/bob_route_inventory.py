"""FR #8835: source-derived inventory of BobCallback /bob/v1 routes (stdlib only).

Parses path-constant assignments from bobcallback.py (and related modules) via
``ast``. Does not import project modules. Used by the webhook docs coverage test.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RouteConstant:
    name: str
    path: str
    source: str
    line: int


_EXCLUDE_PREFIXES = ("/jeeves",)
# Retired routes kept as named constants for 404/redirect handlers — not separate docs cards.
_EXCLUDE_PATHS = frozenset({"/bob/v1/models/validate"})


def _const_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def parse_path_constants(source: str, *, filename: str = "<source>") -> list[RouteConstant]:
    """Return NAME = \"/path\" assignments from module source text."""
    tree = ast.parse(source, filename=filename)
    out: list[RouteConstant] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        name = target.id
        if not name.endswith("_PATH") and name not in ("PUBLIC_DIGEST_PATH",):
            continue
        value = _const_str(node.value)
        if value is None and isinstance(node.value, ast.Attribute):
            # e.g. MODELS_PATH = models_catalog.MODELS_PATH — resolve later via alias map
            continue
        if value is None:
            continue
        out.append(
            RouteConstant(name=name, path=value, source=filename, line=getattr(node, "lineno", 0))
        )
    return out


def parse_attribute_path_aliases(
    source: str,
    *,
    filename: str = "<source>",
    resolved: dict[str, str] | None = None,
) -> list[RouteConstant]:
    """Resolve ``FOO_PATH = other.BAR_PATH`` when ``resolved`` already knows BAR_PATH."""
    resolved = resolved or {}
    tree = ast.parse(source, filename=filename)
    out: list[RouteConstant] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or not target.id.endswith("_PATH"):
            continue
        val = node.value
        if isinstance(val, ast.Attribute) and isinstance(val.value, ast.Name):
            key = f"{val.value.id}.{val.attr}"
            # Also allow attr-only lookup by attr name
            path = resolved.get(key) or resolved.get(val.attr)
            if path:
                out.append(
                    RouteConstant(
                        name=target.id,
                        path=path,
                        source=filename,
                        line=getattr(node, "lineno", 0),
                    )
                )
    return out


def parse_module_file(path: Path) -> list[RouteConstant]:
    text = path.read_text(encoding="utf-8-sig")
    return parse_path_constants(text, filename=str(path))


def inventory_bobcallback_tree(repo_root: Path) -> list[RouteConstant]:
    """Collect public/local HTTP path constants from common/scripts."""
    scripts = repo_root / "common" / "scripts"
    files = [
        scripts / "models_catalog.py",
        scripts / "builds_catalog.py",
        scripts / "bobhours.py",
        scripts / "bobcallback.py",
    ]
    resolved: dict[str, str] = {}
    collected: list[RouteConstant] = []
    for f in files:
        if not f.is_file():
            continue
        text = f.read_text(encoding="utf-8-sig")
        for c in parse_path_constants(text, filename=str(f)):
            resolved[c.name] = c.path
            collected.append(c)
        for c in parse_attribute_path_aliases(text, filename=str(f), resolved=resolved):
            resolved[c.name] = c.path
            collected.append(c)
    # De-dupe by path, prefer bobcallback names
    by_path: dict[str, RouteConstant] = {}
    for c in collected:
        if any(c.path.startswith(p) for p in _EXCLUDE_PREFIXES):
            continue
        if c.path in _EXCLUDE_PATHS:
            continue
        prev = by_path.get(c.path)
        if prev is None or "bobcallback" in c.source.replace("\\", "/"):
            by_path[c.path] = c
    return sorted(by_path.values(), key=lambda r: r.path)


def parse_iis_bob_webhook_rules(install_ps1_text: str) -> list[dict[str, str]]:
    """Extract Bob*Webhook rewrite rule names + patterns from Install-BobWebhooks.ps1 text."""
    rules: list[dict[str, str]] = []
    # Match name="BobFooWebhook" ... match url="^bob/v1/..."
    for m in re.finditer(
        r'name="(Bob\w*Webhook)"[^>]*>.*?url="([^"]+)"',
        install_ps1_text,
        flags=re.I | re.S,
    ):
        rules.append({"name": m.group(1), "pattern": m.group(2)})
    return rules


def coverage_paths(repo_root: Path) -> list[str]:
    """Normalised path strings the docs coverage test must document."""
    return [c.path for c in inventory_bobcallback_tree(repo_root)]
