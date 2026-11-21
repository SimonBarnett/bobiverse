/* FR #8703: Plan Agent card. MSI href is the skills-visionary latest asset
 * only after a non-draft plan-v* release exists. Otherwise the card says
 * "not yet released" and has no download link.
 */
(function (root) {
  var API = 'https://api.github.com/repos/SimonBarnett/skills-visionary/releases?per_page=100';
  var MSI_HREF = 'https://github.com/SimonBarnett/skills-visionary/releases/latest/download/PlanAgent.msi';
  var SHA_HREF = MSI_HREF + '.sha256';
  var NOTES_HREF = 'https://github.com/SimonBarnett/skills-visionary/releases/latest';
  var TAG_RE = /^plan-v/i;
  var EMPTY = 'not yet released';

  function pick(releases) {
    var list = releases || [];
    var i, rel, tag;
    for (i = 0; i < list.length; i++) {
      rel = list[i];
      if (!rel || rel.draft || rel.prerelease) continue;
      tag = String(rel.tag_name || '');
      if (TAG_RE.test(tag)) return rel;
    }
    for (i = 0; i < list.length; i++) {
      rel = list[i];
      if (!rel || rel.draft) continue;
      tag = String(rel.tag_name || '');
      if (TAG_RE.test(tag)) return rel;
    }
    return null;
  }

  function clearAssets(el) {
    if (!el) return;
    while (el.firstChild) el.removeChild(el.firstChild);
  }

  function addLink(el, href, label, className) {
    var a = document.createElement('a');
    a.className = className;
    a.href = href;
    a.textContent = label;
    if (label === 'Download Plan Agent') a.setAttribute('data-role', 'msi');
    if (label === 'sha256') a.setAttribute('data-role', 'sha256');
    el.appendChild(a);
  }

  function showEmpty(card) {
    var versionEl = card.querySelector('[data-role="version"]');
    if (versionEl) versionEl.textContent = EMPTY;
    clearAssets(card.querySelector('[data-role="assets"]'));
    var notes = card.querySelector('[data-role="release-notes"]');
    if (notes && notes.parentNode) notes.parentNode.removeChild(notes);
  }

  function showRelease(card, rel) {
    var versionEl = card.querySelector('[data-role="version"]');
    var tag = String(rel.tag_name || '');
    var published = String(rel.published_at || '');
    var day = published.length >= 10 ? published.slice(0, 10) : '';
    var line = tag;
    if (day) line = tag + ' · ' + day;
    if (versionEl) versionEl.textContent = line;
    var assetsEl = card.querySelector('[data-role="assets"]');
    clearAssets(assetsEl);
    if (assetsEl) {
      addLink(assetsEl, MSI_HREF, 'Download Plan Agent', 'btn btn-gold');
      addLink(assetsEl, SHA_HREF, 'sha256', 'btn btn-ghost');
    }
    var notes = card.querySelector('[data-role="release-notes"]');
    if (!notes) {
      notes = document.createElement('a');
      notes.className = 'btn btn-ghost';
      notes.setAttribute('data-role', 'release-notes');
      notes.textContent = 'Release notes';
      card.appendChild(notes);
    }
    notes.href = NOTES_HREF;
  }

  function refresh(card, fetchImpl) {
    var fn = fetchImpl || fetch;
    return fn(API, { headers: { Accept: 'application/vnd.github+json' } })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (payload) {
        var rel = pick(payload);
        if (!rel) { showEmpty(card); return; }
        showRelease(card, rel);
      })
      .catch(function () { showEmpty(card); });
  }

  function boot() {
    var card = document.querySelector('[data-product="plan-agent"]');
    if (!card) return;
    refresh(card);
  }

  var api = { refresh: refresh, pick: pick, MSI_HREF: MSI_HREF, EMPTY: EMPTY };
  root.BobiversePlanAgentDownloads = api;
  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', boot);
    } else {
      boot();
    }
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);
