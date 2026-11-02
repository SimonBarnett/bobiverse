#!/usr/bin/env node
/**
 * FR #5948: service-owned read-only Priority form walk for Airc PRIORITY
 * formStart | subform | getRows.
 *
 *   node run-formwalk-readonly.mjs --op formStart --name CUSTOMERS \
 *     --company C --url U --user U [--path SUB] [--offset N] [--limit N]
 *
 * Password: PRIORITY_SDK_PASSWORD env only (never argv, never logged).
 * Last stdout line: JSON {ok, op, form, columns?, rows?, count?, error?}.
 * CAST IRON: no activateStart, no field writes, no FORMPREP / prepare.
 */
'use strict';

import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

function parseArgs(argv) {
  const out = {
    op: 'formStart',
    name: '',
    path: '',
    company: '',
    url: '',
    user: '',
    offset: 0,
    limit: 5,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const a = argv[i];
    const next = argv[i + 1];
    if (a === '--op' && next != null) {
      out.op = String(next);
      i += 1;
    } else if (a === '--name' && next != null) {
      out.name = String(next);
      i += 1;
    } else if (a === '--path' && next != null) {
      out.path = String(next);
      i += 1;
    } else if (a === '--company' && next != null) {
      out.company = String(next);
      i += 1;
    } else if (a === '--url' && next != null) {
      out.url = String(next);
      i += 1;
    } else if (a === '--user' && next != null) {
      out.user = String(next);
      i += 1;
    } else if (a === '--offset' && next != null) {
      out.offset = Number(next) || 0;
      i += 1;
    } else if (a === '--limit' && next != null) {
      out.limit = Number(next) || 5;
      i += 1;
    }
  }
  return out;
}

function emit(payload) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

/** FR #5999: secret-safe bounded message for intake sdk_message (slice 200). */
function boundedMessage(err, maxLen = 200) {
  let s = String((err && (err.message || err)) || '');
  s = s.replace(/(password|passwd|secret|pwd|token)\s*[:=]\s*\S+/gi, '$1=***');
  s = s.replace(/\s+/g, ' ').trim();
  if (s.length > maxLen) s = s.slice(0, maxLen);
  return s;
}

function loadSdk() {
  const candidates = [
    path.join(__dirname, '..', 'node_modules', 'priority-web-sdk'),
    path.join(__dirname, 'node_modules', 'priority-web-sdk'),
  ];
  for (const c of candidates) {
    try {
      return require(c);
    } catch {
      /* try next */
    }
  }
  throw new Error('priority-web-sdk missing');
}

function classifyError(err) {
  const msg = String((err && (err.message || err)) || '').toLowerCase();
  if (
    msg.includes('not found') ||
    msg.includes('formnotfound') ||
    msg.includes('unprepared') ||
    msg.includes('does not exist') ||
    msg.includes('cannot open') ||
    msg.includes('failed to open') ||
    msg.includes('failed to start form') ||
    msg.includes('unknown form') ||
    msg.includes('no such form') ||
    msg.includes('invalid form') ||
    msg.includes('o11')
  ) {
    return 'form-not-found';
  }
  if (
    msg.includes('licence') ||
    msg.includes('license') ||
    msg.includes('access') ||
    msg.includes('forbidden') ||
    msg.includes('denied') ||
    msg.includes('401') ||
    msg.includes('403')
  ) {
    return 'no-access';
  }
  if (
    msg.includes('password') ||
    msg.includes('credential') ||
    msg.includes('need --name')
  ) {
    return 'password-refused';
  }
  return 'sdk-fault';
}

function columnNames(form) {
  const cols = (form && form.columns) || {};
  return Object.keys(cols).filter((k) => k && k !== 'undefined').slice(0, 40);
}

function rowsFromPack(pack, formName, offset, limit) {
  if (!pack || typeof pack !== 'object') return { rows: [], total: 0 };
  const bucket = pack[formName] || pack[Object.keys(pack)[0]] || pack;
  if (!bucket || typeof bucket !== 'object') return { rows: [], total: 0 };
  const keys = Object.keys(bucket).filter((k) => k !== 'undefined' && k !== 'metadata');
  const all = [];
  for (const key of keys) {
    const row = bucket[key];
    if (!row || typeof row !== 'object') continue;
    const clean = {};
    for (const [rk, rv] of Object.entries(row)) {
      if (rk === 'metadata' || typeof rv === 'function') continue;
      if (rv === null || rv === undefined) continue;
      const s = String(rv);
      if (s.length > 120) clean[rk] = `${s.slice(0, 117)}...`;
      else clean[rk] = rv;
    }
    all.push(clean);
  }
  const off = Math.max(0, offset | 0);
  const lim = Math.max(1, Math.min(20, limit | 0 || 5));
  return { rows: all.slice(off, off + lim), total: all.length, offset: off, limit: lim };
}

async function main() {
  const args = parseArgs(process.argv);
  const password = process.env.PRIORITY_SDK_PASSWORD || '';
  const op = String(args.op || 'formStart').trim();
  const formName = String(args.name || '').trim();
  if (!formName || !password) {
    // FR #5991: missing name/password is expected (no intake), never sdk-fault.
    emit({ ok: false, error: 'password-refused', message: 'need --name and PRIORITY_SDK_PASSWORD', op, form: formName });
    process.exit(2);
  }

  let Priority;
  try {
    Priority = loadSdk();
  } catch (e) {
    emit({ ok: false, error: 'sdk_mjs_missing', message: String(e.message || e), op, form: formName });
    process.exit(2);
  }

  const priority = new Priority.Priority({
    url: args.url,
    tabulaini: 'tabula.ini',
    language: 2,
  });

  try {
    await priority.login(args.user, password, args.company);
  } catch (e) {
    // FR #5999: include bounded message so Python intake sdk_message is not empty.
    emit({
      ok: false,
      error: classifyError(e) === 'sdk-fault' ? 'no-access' : classifyError(e),
      message: boundedMessage(e),
      op,
      form: formName,
    });
    process.exit(2);
  }

  let form;
  try {
    // Read-only: formStart only. Never activateStart / setValue / prepare.
    form = await priority.formStart(formName, () => {}, null, { company: args.company }, 1);
  } catch (e) {
    // FR #5999: unclassified throws must carry message for sdk-fault triage.
    emit({
      ok: false,
      error: classifyError(e),
      message: boundedMessage(e),
      op,
      form: formName,
    });
    process.exit(2);
  }

  if (!form) {
    emit({ ok: false, error: 'form-not-found', op, form: formName });
    process.exit(2);
  }

  if (op === 'subform') {
    const subPath = String(args.path || '').trim();
    if (!subPath) {
      emit({ ok: false, error: 'subform-not-found', op, form: formName, path: '' });
      process.exit(2);
    }
    try {
      const sub = await form.startSubForm(subPath);
      if (!sub) {
        emit({ ok: false, error: 'subform-not-found', op, form: formName, path: subPath });
        process.exit(2);
      }
      const cols = columnNames(sub);
      let pack = {};
      try {
        pack = (await sub.getRows(1)) || {};
      } catch (e) {
        emit({
          ok: false,
          error: classifyError(e),
          message: boundedMessage(e),
          op: 'subform',
          form: formName,
          path: subPath,
        });
        process.exit(2);
      }
      const page = rowsFromPack(pack, subPath, args.offset, args.limit);
      emit({
        ok: true,
        op: 'subform',
        form: formName,
        path: subPath,
        columns: cols,
        rows: page.rows,
        count: page.rows.length,
        offset: page.offset,
        limit: page.limit,
        has_more: page.offset + page.limit < page.total,
        readonly: true,
      });
      process.exit(0);
    } catch (e) {
      const err = classifyError(e);
      emit({
        ok: false,
        error: err === 'form-not-found' ? 'subform-not-found' : err,
        message: boundedMessage(e),
        op: 'subform',
        form: formName,
        path: subPath,
      });
      process.exit(2);
    }
  }

  const cols = columnNames(form);
  let pack = {};
  try {
    pack = (await form.getRows(1)) || {};
  } catch (e) {
    emit({
      ok: false,
      error: classifyError(e),
      message: boundedMessage(e),
      op: op === 'getRows' ? 'getRows' : 'formStart',
      form: formName,
    });
    process.exit(2);
  }
  const page = rowsFromPack(pack, formName, args.offset, args.limit);
  const subforms = [];
  try {
    const sf = form.SubForms || form.subforms || {};
    for (const k of Object.keys(sf || {})) {
      if (k && k !== 'undefined') subforms.push(k);
    }
  } catch {
    /* ignore */
  }

  const base = {
    ok: true,
    op: op === 'getRows' ? 'getRows' : 'formStart',
    form: formName,
    columns: cols,
    rows: page.rows,
    count: page.rows.length,
    offset: page.offset,
    limit: page.limit,
    has_more: page.offset + page.limit < page.total,
    readonly: true,
  };
  if (op !== 'getRows') {
    base.title = (form.title || formName);
    base.subforms = subforms.slice(0, 40);
  }
  emit(base);
  process.exit(0);
}

main().catch((e) => {
  emit({
    ok: false,
    error: classifyError(e),
    message: boundedMessage(e),
  });
  process.exit(2);
});
