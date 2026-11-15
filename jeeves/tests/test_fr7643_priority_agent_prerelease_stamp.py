"""FR #7643: Priority Agent card stamps installer including launcher prereleases."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from repo_layout import REPO

WWW = REPO / "jeeves" / "www" / "irc-ntsa"
SCRIPT = WWW / "downloads" / "priority-agent.js"
PAGE = WWW / "downloads" / "index.html"
STAMP = REPO / "jeeves" / "scripts" / "Stamp-PriorityAgentDownloads.ps1"
INSTALL = REPO / "jeeves" / "scripts" / "Install-BobWebhooks.ps1"
HARDCODED_VER = re.compile(r"Priority Agent v\d+\.\d+\.\d+")
_SEMVER = re.compile(r"(?<![\\\d])\d+\.\d+\.\d+(?![\\\d])")

TODAY_SHAPE = [
    {
        "name": "Priority Agent launcher v1.0.74",
        "tag_name": "launcher-v1.0.74",
        "draft": False,
        "prerelease": True,
        "assets": [
            {"name": "PriorityAgent.exe"},
            {"name": "PriorityAgent.exe.sha256"},
        ],
    },
    {
        "name": "Priority Agent (2026-11-06 cycle)",
        "tag_name": "uat-2026-11-06",
        "draft": False,
        "prerelease": False,
        "assets": [],
    },
    {
        "name": "Priority Agent launcher v1.0.1",
        "tag_name": "launcher-v1.0.1",
        "draft": False,
        "prerelease": True,
        "assets": [
            {"name": "PriorityAgent.exe"},
            {"name": "PriorityAgent.exe.sha256"},
        ],
    },
]


def _node_refresh(tmp_path: Path, releases: list, *, fail_api: bool = False) -> dict:
    node = shutil.which("node")
    assert node, "node required"
    runner = tmp_path / "run_pa_7643.js"
    # Pre-stamp the card so API-fail can prove links remain.
    stamped_exe = (
        "https://github.com/SimonBarnett/priority-mcp/releases/download/"
        "launcher-v1.0.74/PriorityAgent.exe"
    )
    stamped_sha = stamped_exe + ".sha256"
    runner.write_text(
        f"""
const fs = require('fs');
const vm = require('vm');
const path = process.argv[2];
const payload = JSON.parse(process.argv[3]);
const failApi = process.argv[4] === '1';
const js = fs.readFileSync(path, 'utf8');
const versionEl = {{ textContent: 'Priority Agent launcher v1.0.74' }};
const notesEl = {{ href: 'https://github.com/SimonBarnett/priority-mcp/releases/tag/launcher-v1.0.74' }};
const gold = {{ href: '{stamped_exe}', textContent: 'PriorityAgent.exe', className: 'btn btn-gold' }};
const sha = {{ href: '{stamped_sha}', textContent: 'sha256', className: 'btn btn-ghost' }};
const assetsEl = {{
  children: [gold, sha],
  firstChild: gold,
  appendChild(c) {{
    this.children.push(c);
    this.firstChild = this.children[0];
    return c;
  }},
  removeChild(c) {{
    this.children = this.children.filter(function (x) {{ return x !== c; }});
    this.firstChild = this.children[0] || null;
    return c;
  }}
}};
const card = {{
  querySelector(sel) {{
    if (sel.indexOf('version') !== -1) return versionEl;
    if (sel.indexOf('assets') !== -1) return assetsEl;
    if (sel.indexOf('release-notes') !== -1) return notesEl;
    return null;
  }}
}};
function el(tag) {{
  return {{ tagName: tag, className: '', href: '', textContent: '', setAttribute() {{}} }};
}}
const intakePosts = [];
const ctx = {{
  console: console,
  document: {{ createElement: el, querySelector() {{ return card; }} }},
  sessionStorage: {{
    _m: Object.create(null),
    getItem(k) {{ return Object.prototype.hasOwnProperty.call(this._m, k) ? this._m[k] : null; }},
    setItem(k, v) {{ this._m[k] = String(v); }}
  }},
  fetch(url, opts) {{
    const u = String(url || '');
    if (u.indexOf('/bob/v1/intake') !== -1) {{
      intakePosts.push({{ url: u, body: opts && opts.body ? String(opts.body) : '' }});
      return Promise.resolve({{ ok: true, status: 202, json() {{ return Promise.resolve({{ queued: true }}); }} }});
    }}
    if (failApi) return Promise.reject(new Error('blocked'));
    return Promise.resolve({{ ok: true, json() {{ return Promise.resolve(payload); }} }});
  }},
  globalThis: null
}};
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(js, ctx);
const api = ctx.BobiversePriorityAgentDownloads;
api.refresh(card, ctx.fetch).then(function () {{
  const out = {{
    version: versionEl.textContent,
    notesHref: notesEl.href,
    hrefs: assetsEl.children.map(function (c) {{ return c.href; }}),
    labels: assetsEl.children.map(function (c) {{ return c.textContent; }}),
    intakePosts: intakePosts,
    picked: api.pickLatest(payload)
  }};
  process.stdout.write(JSON.stringify(out));
}}).catch(function (e) {{ console.error(e); process.exit(1); }});
""",
        encoding="utf-8",
    )
    r = subprocess.run(
        [node, str(runner), str(SCRIPT), json.dumps(releases), "1" if fail_api else "0"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_fr7643_today_shape_picks_prerelease_launcher(tmp_path: Path):
    out = _node_refresh(tmp_path, TODAY_SHAPE)
    assert out["picked"] and out["picked"]["tag_name"] == "launcher-v1.0.74"
    hrefs = " ".join(out["hrefs"])
    assert (
        "priority-mcp/releases/download/launcher-v1.0.74/PriorityAgent.exe" in hrefs
    )
    assert "PriorityAgent.exe.sha256" in hrefs
    assert "uat-2026-11-06" not in hrefs


def test_fr7643_api_fail_keeps_stamped_links(tmp_path: Path):
    out = _node_refresh(tmp_path, TODAY_SHAPE, fail_api=True)
    hrefs = " ".join(out["hrefs"])
    assert "launcher-v1.0.74/PriorityAgent.exe" in hrefs
    assert "PriorityAgent.exe.sha256" in hrefs
    assert "Could not refresh" not in out["version"]


def test_fr7643_stamp_script_writes_concrete_hrefs(tmp_path: Path):
    assert STAMP.is_file()
    html_src = PAGE.read_text(encoding="utf-8")
    html_path = tmp_path / "index.html"
    html_path.write_text(html_src, encoding="utf-8")
    fixture = tmp_path / "releases.json"
    fixture.write_text(json.dumps(TODAY_SHAPE), encoding="utf-8")
    r = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-File",
            str(STAMP),
            "-HtmlPath",
            str(html_path),
            "-ReleasesJsonPath",
            str(fixture),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    stamped = html_path.read_text(encoding="utf-8")
    assert (
        "https://github.com/SimonBarnett/priority-mcp/releases/download/launcher-v1.0.74/PriorityAgent.exe"
        in stamped
    )
    assert "PriorityAgent.exe.sha256" in stamped
    assert 'data-role="installer"' in stamped
    assert "releases/tag/launcher-v1.0.74" in stamped
    # Source tree must not hardcode the live tag (stamp only).
    assert "launcher-v1.0.74" not in PAGE.read_text(encoding="utf-8")


def test_fr7643_install_wires_stamp_and_no_hardcoded_semver():
    install = INSTALL.read_text(encoding="utf-8-sig")
    assert "Stamp-PriorityAgentDownloads.ps1" in install
    js = SCRIPT.read_text(encoding="utf-8")
    html = PAGE.read_text(encoding="utf-8")
    assert "prerelease" in js
    assert "FR #7643" in js or "7643" in js
    assert not HARDCODED_VER.search(js)
    assert not HARDCODED_VER.search(html)
    assert _SEMVER.search(js) is None
    assert "launcher-v" not in html
