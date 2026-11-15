/* FR #7455 / #7528: page-time latest Priority Agent release (priority-mcp). Isolated from Bobiverse MSI refresh. */
(function (root) {
  var OWNER_REPO = 'SimonBarnett/priority-mcp';
  var API = 'https://api.github.com/repos/' + OWNER_REPO + '/releases?per_page=100';
  var DOWNLOAD_PREFIX = 'https://github.com/' + OWNER_REPO + '/releases/download/';
  var NOTES_FALLBACK = 'https://github.com/' + OWNER_REPO + '/releases';
  var TITLE_RE = /^Priority Agent v(\d+)\.(\d+)\.(\d+)$/;

  function cmpVer(a, b) {
    for (var i = 0; i < 3; i++) {
      if (a[i] !== b[i]) return a[i] - b[i];
    }
    return 0;
  }

  function pickLatest(releases) {
    var best = null;
    var bestVer = [-1, -1, -1];
    (releases || []).forEach(function (rel) {
      if (!rel || rel.draft || rel.prerelease) return;
      var m = String(rel.name || '').match(TITLE_RE);
      if (!m) return;
      var ver = [+m[1], +m[2], +m[3]];
      if (cmpVer(ver, bestVer) > 0) {
        bestVer = ver;
        best = rel;
      }
    });
    return best;
  }

  function assetHref(tag, name) {
    return DOWNLOAD_PREFIX + encodeURIComponent(tag) + '/' + encodeURIComponent(name);
  }

  function notesHref(tag) {
    var t = String(tag || '');
    if (!t) return NOTES_FALLBACK;
    return 'https://github.com/' + OWNER_REPO + '/releases/tag/' + encodeURIComponent(t);
  }

  function setNotes(card, tag) {
    var notes = card.querySelector('[data-role="release-notes"]');
    if (!notes) return;
    notes.href = notesHref(tag);
  }

  function render(card, rel) {
    var versionEl = card.querySelector('[data-role="version"]');
    var assetsEl = card.querySelector('[data-role="assets"]');
    if (!rel) {
      if (versionEl) versionEl.textContent = 'No matching Priority Agent release';
      setNotes(card, '');
      return;
    }
    var title = String(rel.name || '');
    if (versionEl) versionEl.textContent = title;
    var tag = String(rel.tag_name || '');
    setNotes(card, tag);
    if (!assetsEl) return;
    while (assetsEl.firstChild) assetsEl.removeChild(assetsEl.firstChild);
    var assets = rel.assets || [];
    assets.forEach(function (a) {
      var name = a && a.name ? String(a.name) : '';
      if (!name) return;
      var link = document.createElement('a');
      link.href = assetHref(tag, name);
      var isSha = /\.sha256$/i.test(name);
      link.className = isSha ? 'btn btn-ghost' : 'btn btn-gold';
      link.textContent = isSha ? 'sha256' : name;
      assetsEl.appendChild(link);
    });
  }

  function refresh(card, fetchImpl) {
    var fn = fetchImpl || fetch;
    return fn(API, { headers: { Accept: 'application/vnd.github+json' } }).then(function (r) {
      if (!r || !r.ok) throw new Error('releases');
      return r.json();
    }).then(function (payload) {
      var list = Array.isArray(payload) ? payload : [];
      render(card, pickLatest(list));
    }).catch(function () {
      var versionEl = card.querySelector('[data-role="version"]');
      if (versionEl) versionEl.textContent = 'Could not refresh Priority Agent releases';
      setNotes(card, '');
    });
  }

  root.BobiversePriorityAgentDownloads = {
    pickLatest: pickLatest,
    render: render,
    refresh: refresh,
    notesHref: notesHref,
    NOTES_FALLBACK: NOTES_FALLBACK,
    API: API
  };

  if (typeof document !== 'undefined' && document.querySelector) {
    var card = document.querySelector('[data-product="priority-agent"]');
    if (card && typeof fetch === 'function') {
      refresh(card, fetch);
    }
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);
