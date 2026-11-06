/**
 * FR #5946 / #6003: optional EFORM → FORMPREPDRCT2 walk for Airc PRIORITY prepare form.
 * Default prepare form uses run-repprep-via-exec.mjs (procStart). This runner is
 * opt-in only: AIRC_PRIORITY_FORM_VIA_EFORM=1 (needs API-licensed user).
 * Password: env PRIORITY_SDK_PASSWORD. Never log it.
 * Last stdout line: JSON {ok, ended, errors} or {ok:false, stage, message, type}.
 *
 * FR #5994: no customer-specific --url/--user/--company defaults; dump under
 * AIRC_HOME / AIRC_INSTALL_ROOT / OS tmp (never fixed C:\\Priority\\tmp).
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

function arg(name, fallback = '') {
  const i = process.argv.indexOf(name);
  if (i >= 0 && i + 1 < process.argv.length) return process.argv[i + 1];
  return fallback;
}

function defaultOutDir() {
  const base =
    process.env.AIRC_HOME ||
    process.env.AIRC_INSTALL_ROOT ||
    process.env.TEMP ||
    process.env.TMPDIR ||
    os.tmpdir();
  return path.join(base, 'tmp', 'airc-formprep', 'sdk-run');
}

function emitFail(stage, message, type) {
  const body = { ok: false, stage, message: String(message || '') };
  if (type) body.type = String(type);
  // stdout so airc_console._priority_sdk_repprep can parse sdk_reason (FR #5994).
  console.log(JSON.stringify(body));
}

const formName = arg('--name');
const procName = arg('--proc', 'FORMPREPDRCT2');
const company = arg('--company');
const url = arg('--url');
const tabulaini = arg('--tabulaini', 'tabula.ini');
const username = arg('--user');
const outDir = arg('--out', defaultOutDir());
const password = process.env.PRIORITY_SDK_PASSWORD || '';
const language = Number(arg('--language', '2')) || 2;

if (!formName || !password || !url || !username || !company) {
  emitFail(
    'args',
    'need --name --url --user --company and PRIORITY_SDK_PASSWORD'
  );
  process.exit(2);
}
fs.mkdirSync(outDir, { recursive: true });

function dump(name, obj) {
  fs.writeFileSync(path.join(outDir, name), JSON.stringify(obj, (k, v) => (typeof v === 'function' ? undefined : v), 2));
}

function publicStep(step) {
  if (!step) return step;
  return {
    type: step.type,
    message: step.message,
    messagetype: step.messagetype,
    input: step.input
      ? {
          title: step.input.title,
          Options: step.input.Options,
          EditField: (step.input.EditField || []).map((f) => ({
            field: f.field,
            title: f.title,
            value: f.value,
          })),
        }
      : undefined,
    proc: step.proc ? { name: step.proc.name, title: step.proc.title } : undefined,
    hyperlinks: step.hyperlinks,
    Urls: step.Urls,
    formats: step.formats,
  };
}

function columnMeta(form) {
  const cols = form && form.columns ? form.columns : {};
  const out = {};
  for (const k of Object.keys(cols)) {
    const c = cols[k] || {};
    out[k] = {
      title: c.title,
      type: c.type,
      iskey: c.iskey,
      maxLength: c.maxLength,
      readonly: c.readonly,
    };
  }
  return out;
}

function rowsFromPack(errRows, formNameHint) {
  if (!errRows || typeof errRows !== 'object') return [];
  const pack = errRows[formNameHint] || errRows[Object.keys(errRows)[0]] || {};
  const rows = [];
  for (const key of Object.keys(pack)) {
    if (key === 'undefined') continue;
    const row = pack[key];
    if (!row || typeof row !== 'object') continue;
    rows.push(row);
  }
  return rows;
}

function typeSeverity(type) {
  const t = String(type || '').trim().toUpperCase();
  if (t === 'I' || t === 'INFO' || t === 'INFORMATION') return 'Info';
  return 'Warning';
}

function rowToPrepError(row, wantedName) {
  const type = row.TYPE;
  const msg = [row.CMESSAGE, row.MESSAGE, row.TEXT, row.ERRMSG, row.MSG, row.TITLE]
    .find((v) => v !== undefined && v !== null && String(v).trim() !== '');
  const blob = Object.keys(row)
    .filter((k) => k !== 'metadata' && row[k] !== undefined && row[k] !== null && String(row[k]).trim() !== '')
    .map((k) => k + '=' + String(row[k]).trim())
    .join('; ');
  const text = msg ? String(msg).trim() : blob;
  if (!text) return null;
  const line = type ? (String(type).trim() + ': ' + text) : text;
  const mentions = new RegExp(wantedName, 'i').test(line);
  return {
    source: 'FORMPREPERRS',
    severity: typeSeverity(type),
    formHint: mentions ? wantedName : '',
    text: line,
  };
}

async function collectRows(form) {
  const all = [];
  const seen = new Set();
  const win = Number(form.windowSize) || 20;
  let from = 1;
  for (let page = 0; page < 25; page += 1) {
    const raw = await form.getRows(from);
    const rows = rowsFromPack(raw, form.name);
    if (rows.length === 0) break;
    let added = 0;
    for (const row of rows) {
      const sig = JSON.stringify(row);
      if (seen.has(sig)) continue;
      seen.add(sig);
      all.push(row);
      added += 1;
    }
    if (rows.length < win || added === 0) break;
    from += rows.length;
  }
  return all;
}

const sdkMod = await import('priority-web-sdk');
const priority = sdkMod.default || sdkMod;
const errors = [];
const steps = [];

try {
  await priority.login({
    url,
    tabulaini,
    language,
    profile: { company },
    appname: 'ce-formprep-agent',
    username,
    password,
    devicename: 'agentic_fomprep',
  });
} catch (e) {
  dump('login-error.json', { message: e.message, type: e.type });
  emitFail('login', e.message, e.type);
  process.exit(2);
}

let eform;
try {
  eform = await priority.formStart(
    'EFORM',
    (sr) => {
      if (sr && sr.message) errors.push({ source: 'sdk', severity: sr.type === 'error' ? 'Warning' : 'Info', text: String(sr.message) });
      if (sr && sr.type === 'warning' && eform.warningConfirm) eform.warningConfirm(1);
      if (sr && sr.type === 'information' && eform.infoMsgConfirm) eform.infoMsgConfirm();
    },
    null,
    { company },
    0
  );
} catch (e) {
  dump('formstart-error.json', { message: e.message, type: e.type });
  emitFail('formStart', e.message, e.type);
  process.exit(2);
}

try {
  await eform.setSearchFilter({
    or: 0,
    QueryValues: [{ field: 'ENAME', fromval: formName, toval: '', op: '=', sort: 0, isdesc: 0 }],
  });
  const rows = await eform.getRows(1);
  dump('eform-rows.json', rows);
  const pack = rows && rows.EFORM ? rows.EFORM : {};
  const idxs = Object.keys(pack).filter((k) => k !== 'undefined');
  const matched = idxs.filter((k) => {
    const row = pack[k] || {};
    return String(row.ENAME || '').trim() === formName;
  });
  if (matched.length !== 1) {
    emitFail(
      'search',
      matched.length < 1
        ? 'form not found in EFORM: ' + formName
        : 'EFORM ENAME not unique for ' + formName + ' rows=' + matched.length
    );
    process.exit(2);
  }
  const idx = Number(matched[0]);
  await eform.setActiveRow(idx);
} catch (e) {
  dump('search-error.json', { message: e.message, type: e.type });
  emitFail('search', e.message, e.type);
  process.exit(2);
}

function displayUrlOf(step) {
  const urls = step && (step.Urls || step.urls);
  if (!urls) return '';
  if (typeof urls === 'string') return urls;
  if (urls.url) return String(urls.url);
  if (Array.isArray(urls) && urls[0]) return String(urls[0].url || urls[0]);
  return '';
}

async function scrapeFormPrepErrs() {
  dump('eform-subforms.json', (eform && eform.subForms) || {});
  let errForm = null;
  const onErrMsg = (sr) => {
    if (sr && sr.type === 'warning' && errForm && errForm.warningConfirm) errForm.warningConfirm(1);
    if (sr && sr.type === 'information' && errForm && errForm.infoMsgConfirm) errForm.infoMsgConfirm();
  };
  try {
    errForm = await priority.formStart('FORMPREPERRS', onErrMsg, null, { company }, 1);
  } catch (e) {
    dump('formprep-errs-error.json', { message: e.message, type: e.type });
    errors.push({ source: 'FORMPREPERRS', severity: 'Info', text: 'FORMPREPERRS open failed: ' + e.message });
    return;
  }
  dump('formprep-errs-meta.json', {
    via: 'formStart',
    name: errForm.name,
    title: errForm.title,
    ishtml: errForm.ishtml,
    oneline: errForm.oneline,
    windowSize: errForm.windowSize,
    columns: columnMeta(errForm),
    subForms: errForm.subForms || {},
  });
  try {
    const errRows = await collectRows(errForm);
    dump('formprep-errs-rows.json', errRows);
    for (const row of errRows) {
      const item = rowToPrepError(row, formName);
      if (item) errors.push(item);
    }
  } catch (e) {
    dump('formprep-errs-rows-error.json', { message: e.message, type: e.type });
    errors.push({ source: 'FORMPREPERRS', severity: 'Info', text: 'FORMPREPERRS getRows failed: ' + e.message });
  }
  try { await errForm.endCurrentForm(); } catch { /* ignore */ }
}

let step;
let activateFailed = null;
try {
  step = await eform.activateStart(procName, 'P', null);
} catch (e) {
  activateFailed = e;
  dump('activate-error.json', { message: e.message, type: e.type });
  errors.push({ source: 'sdk', severity: 'Warning', text: 'activateStart: ' + e.message });
}

const deadline = Date.now() + 180000;
let n = 0;
while (!activateFailed && step && Date.now() < deadline && n < 40) {
  n += 1;
  const snap = publicStep(step);
  steps.push(snap);
  dump(`step-${String(n).padStart(2, '0')}.json`, snap);
  const type = step.type;
  const proc = step.proc;
  if (type === 'end') break;
  if (type === 'message') {
    const sev = step.messagetype === 'error' ? 'Warning' : 'Info';
    errors.push({ source: 'sdk', severity: sev, text: String(step.message || '') });
    step = await proc.message(1);
    continue;
  }
  if (type === 'inputHelp') {
    step = await proc.inputHelp(1);
    continue;
  }
  if (type === 'inputOptions') {
    const opts = (step.input && step.input.Options) || [];
    const sel = (opts.find((o) => o.selected) || opts[0] || {}).field;
    step = await proc.inputOptions(1, sel);
    continue;
  }
  if (type === 'inputFields') {
    const fields = (step.input && step.input.EditField) || [];
    const data = {
      EditFields: fields.map((f) => ({
        field: f.field,
        op: 0,
        value: /form|ename|exec|name/i.test(String(f.title || '')) ? formName : String(f.value || ''),
      })),
    };
    step = await proc.inputFields(1, data);
    continue;
  }
  if (type === 'reportOptions') {
    const formats = step.formats || [];
    const sel = (formats.find((f) => f.selected) || formats[0] || {}).format;
    step = await proc.reportOptions(1, sel || 0);
    continue;
  }
  if (type === 'documentOptions') {
    const formats = step.formats || [];
    const sel = (formats.find((f) => f.selected) || formats[0] || {}).format;
    step = await proc.documentOptions(1, sel || 0, 2);
    continue;
  }
  if (type === 'displayUrl') {
    const url = displayUrlOf(step);
    errors.push({ source: 'PREPMSG', severity: 'Warning', formHint: formName, text: url || 'displayUrl' });
    if (url && /^https?:/i.test(url)) {
      try {
        const res = await fetch(url);
        const body = await res.text();
        fs.writeFileSync(path.join(outDir, 'prepmsg.html'), body);
        const text = body.replace(/<script[\s\S]*?<\/script>/gi, ' ').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
        if (text) errors.push({ source: 'PREPMSG', severity: 'Warning', formHint: formName, text: text.slice(0, 4000) });
      } catch (e) {
        errors.push({ source: 'PREPMSG', severity: 'Info', text: 'displayUrl fetch failed: ' + e.message });
      }
    }
    step = await proc.continueProc();
    continue;
  }
  if (type === 'client') {
    step = await proc.clientContinue('');
    continue;
  }
  errors.push({ source: 'sdk', severity: 'Warning', text: 'unsupported step ' + type });
  try { await proc.cancel(); } catch { /* ignore */ }
  break;
}

// Scrape before activateEnd so a failed prep's stack is still in this session.
await scrapeFormPrepErrs();
try { await eform.activateEnd(); } catch { /* ignore */ }
try { await eform.endCurrentForm(); } catch { /* ignore */ }

dump('steps.json', steps);
dump('errors.json', errors);
const last = steps.length ? steps[steps.length - 1] : {};
const formprepErrs = errors.filter((e) => e && e.source === 'FORMPREPERRS');
const ended = !activateFailed && last && String(last.type || '').toLowerCase() === 'end';
console.log(JSON.stringify({
  ok: !activateFailed && errors.filter((e) => e && e.severity === 'Warning' && e.source === 'sdk').length === 0,
  ended: Boolean(ended || !activateFailed),
  stage: activateFailed ? 'activateStart' : 'walked',
  steps: steps.length,
  lastType: last.type || null,
  lastMessage: last.message || null,
  formprepErrs: formprepErrs.length,
  errors,
  outDir,
}));
process.exit(activateFailed ? 3 : 0);
