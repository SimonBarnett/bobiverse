"""FR #7558: /downloads Priority Agent picks by installer asset, not exact title."""
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
HARDCODED_VER = re.compile(r"Priority Agent v\d+\.\d+\.\d+")
_SEMVER = re.compile(r"(?<![\\\d])\d+\.\d+\.\d+(?![\\\d])")


def _node_refresh(tmp_path: Path, releases: list) -> dict:
    node = shutil.which("node")
    assert node, "node required for FR #7558 resolver tests"
    assert SCRIPT.is_file()
    runner = tmp_path / "run_pa_7558.js"
    runner.write_text(
        """
const fs = require('fs');
const vm = require('vm');
const path = process.argv[2];
const payload = JSON.parse(process.argv[3]);
const js = fs.readFileSync(path, 'utf8');
const versionEl = { textContent: '' };
const notesEl = { href: 'https://github.com/SimonBarnett/priority-mcp/releases' };
const assetsEl = {
  children: [],
  firstChild: null,
  appendChild(c) {
    this.children.push(c);
    this.firstChild = this.children[0];
    return c;
  },
  removeChild(c) {
    this.children = this.children.filter(function (x) { return x !== c; });
    this.firstChild = this.children[0] || null;
    return c;
  }
};
const card = {
  querySelector(sel) {
    if (sel.indexOf('version') !== -1) return versionEl;
    if (sel.indexOf('assets') !== -1) return assetsEl;
    if (sel.indexOf('release-notes') !== -1) return notesEl;
    return null;
  }
};
function el(tag) {
  return { tagName: tag, className: '', href: '', textContent: '', setAttribute() {} };
}
const intakePosts = [];
const ctx = {
  console: console,
  document: { createElement: el, querySelector() { return card; } },
  sessionStorage: {
    _m: Object.create(null),
    getItem(k) { return Object.prototype.hasOwnProperty.call(this._m, k) ? this._m[k] : null; },
    setItem(k, v) { this._m[k] = String(v); }
  },
  fetch(url, opts) {
    const u = String(url || '');
    if (u.indexOf('/bob/v1/intake') !== -1) {
      intakePosts.push({ url: u, body: opts && opts.body ? String(opts.body) : '' });
      return Promise.resolve({ ok: true, status: 202, json() { return Promise.resolve({ queued: true }); } });
    }
    return Promise.resolve({ ok: true, json() { return Promise.resolve(payload); } });
  },
  globalThis: null
};
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(js, ctx);
const api = ctx.BobiversePriorityAgentDownloads;
if (!api) { console.error('missing export'); process.exit(2); }
api.refresh(card, ctx.fetch).then(function () {
  const out = {
    version: versionEl.textContent,
    notesHref: notesEl.href,
    hrefs: assetsEl.children.map(function (c) { return c.href; }),
    labels: assetsEl.children.map(function (c) { return c.textContent; }),
    intakePosts: intakePosts,
    picked: api.pickLatest(payload)
  };
  process.stdout.write(JSON.stringify(out));
}).catch(function (e) { console.error(e); process.exit(1); });
""",
        encoding="utf-8",
    )
    r = subprocess.run(
        [node, str(runner), str(SCRIPT), json.dumps(releases)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_fr7558_fixture_titles_match_by_installer_asset(tmp_path: Path):
    """Real titles (launcher / cycle) resolve via PriorityAgent.exe, not exact title regex."""
    releases = [
        {
            "name": "Priority Agent (2026-11-06 cycle)",
            "tag_name": "uat-2026-11-06",
            "draft": False,
            "prerelease": False,
            "assets": [],
        },
        {
            "name": "Priority Agent launcher v1.0.74",
            "tag_name": "launcher-v1.0.74",
            "draft": False,
            "prerelease": False,
            "assets": [
                {"name": "PriorityAgent.exe"},
                {"name": "PriorityAgent.exe.sha256"},
            ],
        },
        {
            "name": "Priority Agent v9.9.9",
            "tag_name": "v9.9.9",
            "draft": False,
            "prerelease": False,
            "assets": [{"name": "other.exe"}],
        },
    ]
    out = _node_refresh(tmp_path, releases)
    assert "launcher v1.0.74" in out["version"] or "1.0.74" in out["version"]
    assert "2026-11-06" not in out["version"]
    hrefs = " ".join(out["hrefs"])
    assert "priority-mcp/releases/download/launcher-v1.0.74/PriorityAgent.exe" in hrefs
    assert "PriorityAgent.exe.sha256" in hrefs
    assert out["notesHref"].endswith("/releases/tag/launcher-v1.0.74")


def test_fr7558_skips_prereleases(tmp_path: Path):
    releases = [
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
            "assets": [
                {"name": "PriorityAgent.exe"},
            ],
        },
    ]
    out = _node_refresh(tmp_path, releases)
    assert "2026-11-06" in out["version"]
    hrefs = " ".join(out["hrefs"])
    assert "uat-2026-11-06/PriorityAgent.exe" in hrefs
    assert "launcher-v1.0.74" not in hrefs


def test_fr7558_no_asset_shows_empty_and_reports_intake(tmp_path: Path):
    releases = [
        {
            "name": "Priority Agent launcher v1.0.74",
            "tag_name": "launcher-v1.0.74",
            "draft": False,
            "prerelease": True,
            "assets": [{"name": "PriorityAgent.exe"}],
        },
        {
            "name": "Priority Agent (2026-11-06 cycle)",
            "tag_name": "uat-2026-11-06",
            "draft": False,
            "prerelease": False,
            "assets": [],
        },
    ]
    out = _node_refresh(tmp_path, releases)
    assert "No matching Priority Agent release" in out["version"]
    assert out["hrefs"] == []
    assert out["intakePosts"], "must POST intake when no non-prerelease has the installer"
    body = out["intakePosts"][0]["body"]
    assert "SimonBarnett/bobiverse" in body
    assert "Priority Agent" in body


def test_fr7558_script_and_page_have_no_hardcoded_semver():
    js = SCRIPT.read_text(encoding="utf-8")
    html = PAGE.read_text(encoding="utf-8")
    assert "TITLE_RE" not in js
    assert "PriorityAgent" in js
    assert not HARDCODED_VER.search(js)
    assert not HARDCODED_VER.search(html)
    assert _SEMVER.search(js) is None
    assert "title match only" not in html.lower()
