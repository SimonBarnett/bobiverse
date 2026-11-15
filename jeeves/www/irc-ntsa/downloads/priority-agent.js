/* FR #7455 / #7528 / #7558 / #7643: Priority Agent download (priority-mcp).
 * Pick newest non-draft release with PriorityAgent.exe; include prereleases when
 * that is where the installer is. Stamped hrefs at www install stay if API fails.
 */
(function (root) {
  var OWNER_REPO = 'SimonBarnett/priority-mcp';
  var API = 'https://api.github.com/repos/' + OWNER_REPO + '/releases?per_page=100';
  var DOWNLOAD_PREFIX = 'https://github.com/' + OWNER_REPO + '/releases/download/';
  var NOTES_FALLBACK = 'https://github.com/' + OWNER_REPO + '/releases';
  var INTAKE_URL = 'https://bob.ntsa.uk/bob/v1/intake';
  // Installer: PriorityAgent.exe or PriorityAgent-<digits>.<digits>.<digits>.exe (no stamped versions in source).
  var INSTALLER_RE = /^PriorityAgent(-\d+\.\d+\.\d+)?\.exe$/i;
  var SHA_RE = /^PriorityAgent(-\d+\.\d+\.\d+)?\.exe\.sha256$/i;
  var INTAKE_DEDUP_KEY = 'bobiverse-pa-downloads-missing-v1';

  function assetNames(rel) {
    var out = [];
    var assets = (rel && rel.assets) || [];
    for (var i = 0; i < assets.length; i++) {
      var a = assets[i];
      var name = a && a.name ? String(a.name) : '';
      if (name) out.push(name);
    }
    return out;
  }

  function hasInstaller(rel) {
    var names = assetNames(rel);
    for (var i = 0; i < names.length; i++) {
      if (INSTALLER_RE.test(names[i])) return true;
    }
    return false;
  }

  function pickLatest(releases) {
    // GitHub /releases returns newest first.
    // Pass 1: non-draft non-prerelease with installer.
    // Pass 2: non-draft prerelease with installer (FR #7643 — today's launcher-v* layout).
    var list = releases || [];
    var i, rel;
    for (i = 0; i < list.length; i++) {
      rel = list[i];
      if (!rel || rel.draft || rel.prerelease) continue;
      if (hasInstaller(rel)) return rel;
    }
    for (i = 0; i < list.length; i++) {
      rel = list[i];
      if (!rel || rel.draft) continue;
      if (hasInstaller(rel)) return rel;
    }
    return null;
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

  function reportMissing(fetchImpl) {
    var fn = fetchImpl || fetch;
    try {
      if (typeof sessionStorage !== 'undefined' && sessionStorage.getItem(INTAKE_DEDUP_KEY)) {
        return;
      }
      if (typeof sessionStorage !== 'undefined') {
        sessionStorage.setItem(INTAKE_DEDUP_KEY, '1');
      }
    } catch (e) { /* private mode */ }
    var body = JSON.stringify({
      kind: 'issue',
      repo: 'SimonBarnett/bobiverse',
      title: 'downloads: no Priority Agent installer on any non-draft release',
      body: [
        'bob.ntsa.uk /downloads Priority Agent card found no non-draft',
        'SimonBarnett/priority-mcp release (full or prerelease) with a PriorityAgent.exe',
        '(or PriorityAgent-X.Y.Z.exe) asset. Empty state shown. FR #7643.'
      ].join(' ')
    });
    try {
      fn(INTAKE_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: body
      }).catch(function () { /* ignore */ });
    } catch (e2) { /* ignore */ }
  }

  function render(card, rel) {
    var versionEl = card.querySelector('[data-role="version"]');
    var assetsEl = card.querySelector('[data-role="assets"]');
    if (!rel) {
      if (versionEl) versionEl.textContent = 'No matching Priority Agent release';
      setNotes(card, '');
      if (assetsEl) {
        while (assetsEl.firstChild) assetsEl.removeChild(assetsEl.firstChild);
      }
      return;
    }
    var title = String(rel.name || rel.tag_name || 'Priority Agent');
    if (versionEl) versionEl.textContent = title;
    var tag = String(rel.tag_name || '');
    setNotes(card, tag);
    if (!assetsEl) return;
    while (assetsEl.firstChild) assetsEl.removeChild(assetsEl.firstChild);
    var assets = rel.assets || [];
    assets.forEach(function (a) {
      var name = a && a.name ? String(a.name) : '';
      if (!name) return;
      if (!INSTALLER_RE.test(name) && !SHA_RE.test(name)) return;
      var link = document.createElement('a');
      link.href = assetHref(tag, name);
      var isSha = SHA_RE.test(name);
      link.className = isSha ? 'btn btn-ghost' : 'btn btn-gold';
      link.setAttribute('data-role', isSha ? 'sha256' : 'installer');
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
      var picked = pickLatest(list);
      render(card, picked);
      if (!picked) reportMissing(fn);
    }).catch(function () {
      // FR #7643: keep stamped download / sha256 links when the API is blocked or fails.
    });
  }

  root.BobiversePriorityAgentDownloads = {
    pickLatest: pickLatest,
    hasInstaller: hasInstaller,
    render: render,
    refresh: refresh,
    notesHref: notesHref,
    NOTES_FALLBACK: NOTES_FALLBACK,
    API: API,
    INTAKE_URL: INTAKE_URL
  };

  if (typeof document !== 'undefined' && document.querySelector) {
    var card = document.querySelector('[data-product="priority-agent"]');
    if (card && typeof fetch === 'function') {
      refresh(card, fetch);
    }
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);
