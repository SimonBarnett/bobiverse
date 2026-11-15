"""FR #7465 / #7517: checks and site-kit manifest for the Jeeves IIS www bundle.

No service build. No host names. The #7460 regression is a web.config with a
duplicate staticContent, rewrite, or handlers section.

FR #7517: ship favicon.ico and jeeves/assets in the kit; fail CI when HTML
references a static asset missing from the kit; clean-install smoke GETs those URLs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen
import xml.etree.ElementTree as ET

SECTIONS = ("staticContent", "rewrite", "handlers")
LINK_RE = re.compile(
    r"""(?:href|src)\s*=\s*['"]([^'"]+)['"]""",
    re.IGNORECASE,
)
CSS_URL_RE = re.compile(
    r"""url\(\s*['"]?([^'")]+)['"]?\s*\)""",
    re.IGNORECASE,
)
CSS_IMPORT_RE = re.compile(
    r"""@import\s+(?:url\()?['"]?([^'")]+)['"]?\)?""",
    re.IGNORECASE,
)

# FR #7517: one table for builder, verifier, and tests.
# repo source -> kit-relative path -> public URL after install.
KIT_ASSETS: tuple[tuple[str, str, str], ...] = (
    ("jeeves/www/favicon.ico", "www/favicon.ico", "/favicon.ico"),
    (
        "jeeves/assets/jeeves-butler.ico",
        "assets/jeeves-butler.ico",
        "/jeeves/assets/jeeves-butler.ico",
    ),
    (
        "bob/tray/assets/ntsa-gut-logo.png",
        "assets/ntsa-gut-logo.png",
        "/jeeves/assets/ntsa-gut-logo.png",
    ),
)

# Dynamic routes served by Jeeves / ARR (not static kit files).
DYNAMIC_PREFIXES = ("/bob/v1/",)
DYNAMIC_EXACT = {"/jeeves"}


class KitError(SystemExit):
    pass


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def assert_web_config(path: Path) -> None:
    """Well-formed XML and a single copy of each guarded section."""
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise KitError(f"web.config is not well-formed XML: {exc}") from exc
    counts = {name: 0 for name in SECTIONS}
    for el in root.iter():
        name = local_name(el.tag)
        if name in counts:
            counts[name] += 1
    dupes = {k: v for k, v in counts.items() if v > 1}
    if dupes:
        raise KitError(f"duplicate web.config sections: {dupes}")


def _normalize_ref(raw: str) -> str | None:
    ref = raw.split("#", 1)[0].split("?", 1)[0].strip()
    if not ref or ref.startswith(("#", "mailto:", "javascript:", "data:")):
        return None
    if ref.startswith(("http://", "https://", "//")):
        return None
    return ref


def extract_local_refs(text: str) -> list[str]:
    """Local href/src, CSS url(...), and @import references."""
    out: list[str] = []
    for raw in LINK_RE.findall(text):
        ref = _normalize_ref(raw)
        if ref:
            out.append(ref)
    for raw in CSS_URL_RE.findall(text):
        ref = _normalize_ref(raw)
        if ref:
            out.append(ref)
    for raw in CSS_IMPORT_RE.findall(text):
        ref = _normalize_ref(raw)
        if ref:
            out.append(ref)
    return out


def _asset_paths(html: str) -> list[str]:
    """Backward-compatible name used by older tests."""
    return extract_local_refs(html)


def is_dynamic_route(url_path: str) -> bool:
    """True when the path is proxied to Jeeves / bob API, not a static kit file."""
    path = re.sub(r"/+", "/", url_path or "/")
    if path in DYNAMIC_EXACT:
        return True
    if any(path.startswith(p) for p in DYNAMIC_PREFIXES):
        return True
    # /jeeves/* except static assets and public commands pages
    if path.startswith("/jeeves/"):
        if path.startswith("/jeeves/assets/") or path.startswith("/jeeves/commands"):
            return False
        return True
    return False


def kit_path_for_url(url_path: str, *, out_dir: Path | None = None) -> str:
    """Map a public URL to a path inside the flat kit (www/ + assets/)."""
    path = re.sub(r"/+", "/", url_path or "/")
    if path.startswith("/jeeves/assets/"):
        return "assets/" + path[len("/jeeves/assets/") :]
    rel = path.lstrip("/")
    if not rel or rel.endswith("/"):
        rel = (rel + "index.html") if rel else "index.html"
    kit_rel = "www/" + rel
    if out_dir is not None:
        cand = out_dir / kit_rel
        if cand.is_dir():
            kit_rel = kit_rel.rstrip("/") + "/index.html"
    return kit_rel


def published_path_for_url(url_path: str, *, root: Path | None = None) -> str:
    """Map a public URL to a path under the IIS physical tree."""
    path = re.sub(r"/+", "/", url_path or "/")
    rel = path.lstrip("/")
    if not rel or rel.endswith("/"):
        rel = (rel + "index.html") if rel else "index.html"
    elif root is not None:
        cand = root / rel
        if cand.is_dir():
            rel = (rel.rstrip("/") + "/index.html")
    return rel


def smoke_serve(root: Path, *, strict: bool = True) -> None:
    """Serve the published bundle and require 2xx for pages and local assets.

    FR #7517: when strict, missing static references fail (no is_file skip).
    Dynamic /jeeves and /bob/v1 routes are allowlisted.
    """
    root = root.resolve()

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, fmt: str, *args) -> None:
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        pages = [p for p in root.rglob("*.html")]
        if not pages:
            raise KitError(f"no html pages under {root}")
        seen: set[str] = set()
        for page in pages:
            rel = page.relative_to(root).as_posix()
            _get(base, "/" + rel)
            html = page.read_text(encoding="utf-8", errors="replace")
            for ref in extract_local_refs(html):
                if ref.startswith("/"):
                    url_path = ref
                else:
                    parent = page.parent.relative_to(root).as_posix()
                    url_path = "/" + (parent + "/" if parent != "." else "") + ref
                url_path = re.sub(r"/+", "/", url_path)
                if url_path in seen:
                    continue
                seen.add(url_path)
                if is_dynamic_route(url_path):
                    continue
                rel_disk = published_path_for_url(url_path, root=root)
                target = (root / rel_disk).resolve()
                try:
                    target.relative_to(root)
                except ValueError:
                    continue
                if not target.is_file():
                    if strict:
                        raise KitError(
                            f"missing linked asset {url_path} (from {rel})"
                        )
                    continue
                get_path = "/" + target.relative_to(root).as_posix()
                _get(base, get_path)
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def _get(base: str, path: str) -> bytes:
    url = base + path
    try:
        with urlopen(url, timeout=10) as resp:
            code = getattr(resp, "status", 200)
            if code >= 400:
                raise KitError(f"{url} returned {code}")
            return resp.read()
    except HTTPError as exc:
        if exc.code >= 400:
            raise KitError(f"{url} returned {exc.code}") from exc
        raise


def file_matches(pattern: str, path: str) -> bool:
    pat = pattern.replace("\\", "/").lstrip("./")
    rel = path.replace("\\", "/").lstrip("./")
    if pat.startswith("!"):
        pat = pat[1:]
    rx = re.escape(pat).replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    if re.fullmatch(rx, rel):
        return True
    if pat.endswith("/**") and (rel == pat[:-3] or rel.startswith(pat[:-3] + "/")):
        return True
    return False


def workflow_paths(text: str, event: str) -> list[str]:
    """Return the paths: list under pull_request or push. Ignores paths-ignore."""
    lines = text.splitlines()
    in_event = False
    in_paths = False
    out: list[str] = []
    for line in lines:
        if re.match(rf"^  {event}:\s*$", line):
            in_event = True
            in_paths = False
            continue
        if in_event and re.match(r"^  [A-Za-z0-9_]+:\s*$", line):
            break
        if in_event and re.match(r"^    paths:\s*$", line):
            in_paths = True
            continue
        if in_paths:
            if line.startswith("      - "):
                raw = line.strip()[2:].strip()
                if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
                    raw = raw[1:-1]
                out.append(raw)
                continue
            if line.startswith("    ") and not line.startswith("      "):
                in_paths = False
    return out


def file_selected(patterns: list[str], path: str) -> bool:
    included = False
    for pat in patterns:
        neg = pat.startswith("!")
        if file_matches(pat, path):
            included = not neg
    return included


def workflow_runs(patterns: list[str], changed: list[str]) -> bool:
    return any(file_selected(patterns, p) for p in changed)


def copy_kit_assets(repo: Path, out_dir: Path) -> None:
    """Copy KIT_ASSETS into the flat kit. Fail if a source is missing."""
    assets_root = out_dir / "assets"
    if assets_root.exists():
        shutil.rmtree(assets_root)
    for src_rel, kit_rel, _url in KIT_ASSETS:
        src = repo / src_rel
        if not src.is_file():
            raise KitError(f"missing kit asset source: {src_rel}")
        dest = out_dir / kit_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def write_site_kit(
    www: Path,
    installer: Path,
    out_dir: Path,
    commit: str,
    *,
    repo: Path | None = None,
) -> Path:
    """Build the flat kit: www/, assets/, installer, MANIFEST.json (FR #7517)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle = out_dir / "www"
    if bundle.exists():
        shutil.rmtree(bundle)
    shutil.copytree(www, bundle)
    inst_dest = out_dir / installer.name
    shutil.copy2(installer, inst_dest)
    root = repo if repo is not None else _infer_repo_from_installer(installer)
    copy_kit_assets(root, out_dir)
    files = [p for p in out_dir.rglob("*") if p.is_file() and p.name != "MANIFEST.json"]
    entries = []
    for p in sorted(files):
        rel = p.relative_to(out_dir).as_posix()
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        entries.append({"path": rel, "sha256": digest})
    manifest = {
        "kit": "jeeves-webhooks",
        "commit": commit,
        "files": entries,
    }
    dest = out_dir / "MANIFEST.json"
    dest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return dest


def _infer_repo_from_installer(installer: Path) -> Path:
    # jeeves/scripts/Install-BobWebhooks.ps1 -> repo root
    return installer.resolve().parents[2]


def verify_site_kit(out_dir: Path) -> None:
    """Re-hash MANIFEST, require KIT_ASSETS paths, resolve HTML/CSS static refs."""
    out_dir = out_dir.resolve()
    man_path = out_dir / "MANIFEST.json"
    if not man_path.is_file():
        raise KitError("missing MANIFEST.json")
    data = json.loads(man_path.read_text(encoding="utf-8"))
    entries = {e["path"]: e["sha256"] for e in data.get("files") or []}
    missing_assets: list[str] = []
    for _src, kit_rel, _url in KIT_ASSETS:
        if kit_rel not in entries:
            missing_assets.append(kit_rel)
            continue
        path = out_dir / kit_rel
        if not path.is_file():
            missing_assets.append(kit_rel)
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entries[kit_rel]:
            raise KitError(f"hash mismatch for {kit_rel}")
    if missing_assets:
        raise KitError(f"kit missing required assets: {missing_assets}")

    # Re-hash every listed entry
    for rel, expected in entries.items():
        path = out_dir / rel
        if not path.is_file():
            raise KitError(f"manifest path missing on disk: {rel}")
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got != expected:
            raise KitError(f"hash mismatch for {rel}")

    problems: list[str] = []
    for page in list(out_dir.rglob("*.html")) + list(out_dir.rglob("*.css")):
        rel_page = page.relative_to(out_dir).as_posix()
        text = page.read_text(encoding="utf-8", errors="replace")
        for ref in extract_local_refs(text):
            if ref.startswith("/"):
                url_path = ref
            else:
                # refs relative to www/ pages live under www/
                parent = page.parent.relative_to(out_dir).as_posix()
                url_path = "/" + (parent + "/" if parent != "." else "") + ref
                # strip leading /www when mapping kit-internal relative refs already under www
                if url_path.startswith("/www/"):
                    url_path = url_path[4:]  # keep leading /
                    if not url_path.startswith("/"):
                        url_path = "/" + url_path
            url_path = re.sub(r"/+", "/", url_path)
            # Relative refs inside www/ resolve to kit www/ paths, not public URLs.
            if not ref.startswith("/"):
                kit_rel = (page.parent.relative_to(out_dir) / ref).as_posix()
                kit_rel = re.sub(r"/+", "/", kit_rel)
                target = out_dir / kit_rel
                if target.is_dir():
                    target = target / "index.html"
                    kit_rel = target.relative_to(out_dir).as_posix()
                if not target.is_file():
                    problems.append(f"{rel_page} -> {kit_rel}")
                continue
            if is_dynamic_route(url_path):
                continue
            kit_rel = kit_path_for_url(url_path, out_dir=out_dir)
            target = out_dir / kit_rel
            if not target.is_file():
                problems.append(f"{rel_page} -> {kit_rel} ({url_path})")
    if problems:
        raise KitError(
            "kit HTML/CSS references missing assets:\n  " + "\n  ".join(problems)
        )


def _run_installer(
    ps: str,
    installer: Path,
    physical: Path,
    *,
    www_source: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        ps,
        "-NoProfile",
        "-File",
        str(installer),
        "-SiteKit",
        "-PhysicalPath",
        str(physical),
        "-Backend",
        "http://127.0.0.1:7700",
    ]
    if www_source is not None:
        cmd.extend(["-WwwSource", str(www_source)])
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def _assert_published_kit_assets(physical: Path, kit_dir: Path) -> None:
    """GET each KIT_ASSETS URL via smoke server; bytes must match kit copy."""
    physical = physical.resolve()
    for _src, kit_rel, url in KIT_ASSETS:
        pub_rel = published_path_for_url(url)
        pub = physical / pub_rel
        if not pub.is_file():
            raise KitError(f"clean install missing published asset {pub_rel} ({url})")
        kit_bytes = (kit_dir / kit_rel).read_bytes()
        if pub.read_bytes() != kit_bytes:
            raise KitError(f"published asset bytes differ from kit: {url}")
    # Explicit HTTP 200 + body check
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(physical), **kwargs)

        def log_message(self, fmt: str, *args) -> None:
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        for _src, kit_rel, url in KIT_ASSETS:
            body = _get(base, url)
            if body != (kit_dir / kit_rel).read_bytes():
                raise KitError(f"GET {url} body != kit {kit_rel}")
        cfg = (physical / "web.config").read_text(encoding="utf-8", errors="replace")
        if "/jeeves/assets/" not in cfg:
            raise KitError("web.config missing /jeeves/assets/ rewrite exclusion")
        if ".ico" not in cfg or "image/x-icon" not in cfg:
            raise KitError("web.config missing .ico MIME mapping")
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def run_site_kit(repo: Path, physical: Path, out_dir: Path, commit: str) -> None:
    www = repo / "jeeves" / "www" / "irc-ntsa"
    installer = repo / "jeeves" / "scripts" / "Install-BobWebhooks.ps1"
    ps = shutil.which("powershell") or shutil.which("pwsh")
    if not ps:
        raise KitError("powershell or pwsh required")
    proc = _run_installer(ps, installer, physical, www_source=www)
    if proc.returncode != 0:
        raise KitError(proc.stdout + "\n" + proc.stderr)
    cfg = physical / "web.config"
    assert_web_config(cfg)
    raw = cfg.read_bytes()
    again = _run_installer(ps, installer, physical, www_source=www)
    if again.returncode != 0:
        raise KitError(again.stdout + "\n" + again.stderr)
    if (physical / "web.config").read_bytes() != raw:
        raise KitError("second site-kit install changed web.config bytes")
    smoke_serve(physical, strict=True)
    write_site_kit(www, installer, out_dir, commit, repo=repo)
    verify_site_kit(out_dir)

    # FR #7517: isolated clean install from a kit copy (no checkout WwwSource).
    with tempfile.TemporaryDirectory(prefix="jeeves-kit-clean-") as tmp:
        kit_copy = Path(tmp) / "kit"
        shutil.copytree(out_dir, kit_copy)
        clean_phys = Path(tmp) / "published"
        clean_phys.mkdir()
        kit_installer = kit_copy / "Install-BobWebhooks.ps1"
        clean = _run_installer(ps, kit_installer, clean_phys, www_source=None)
        if clean.returncode != 0:
            raise KitError(
                "clean kit install failed:\n" + clean.stdout + "\n" + clean.stderr
            )
        assert_web_config(clean_phys / "web.config")
        smoke_serve(clean_phys, strict=True)
        _assert_published_kit_assets(clean_phys, kit_copy)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo-root", default=".")
    p.add_argument("--physical", default="")
    p.add_argument("--out", required=True)
    p.add_argument("--commit", default="")
    args = p.parse_args(argv)
    repo = Path(args.repo_root).resolve()
    physical = Path(args.physical) if args.physical else Path(args.out) / "published"
    commit = args.commit or os.environ.get("WORKFLOW_COMMIT") or "unknown"
    try:
        run_site_kit(repo, physical, Path(args.out), commit)
    except KitError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
