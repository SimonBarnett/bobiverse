#!/usr/bin/env node
/**
 * FR #5905: service-owned REPPREPDIRECT2 walk for Airc PRIORITY prepare.
 *
 * Invoked by airc_console._priority_sdk_repprep:
 *   node run-repprep-via-exec.mjs --name ENAME --company C --url U --user U --proc REPPREPDIRECT2
 *
 * Password: PRIORITY_SDK_PASSWORD env only (never argv, never logged).
 * Last stdout line must be one JSON object: {ok, ended, errors}.
 *
 * Resolves priority-web-sdk from ../node_modules (packed next to this file).
 */
'use strict';

import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

function parseArgs(argv) {
  const out = {
    name: '',
    company: '',
    url: '',
    user: '',
    proc: 'REPPREPDIRECT2',
  };
  for (let i = 2; i < argv.length; i += 1) {
    const a = argv[i];
    const next = argv[i + 1];
    if (a === '--name' && next != null) {
      out.name = String(next);
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
    } else if (a === '--proc' && next != null) {
      out.proc = String(next);
      i += 1;
    }
  }
  return out;
}

function emit(payload) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function fieldTitle(row) {
  return String(row.title || row.name || row.fieldName || '')
    .toUpperCase()
    .trim();
}

/**
 * Prefer exact title, then ENAME (when want is NAME), then word-boundary matches.
 * FR #5916: do not let substring includes('NAME') bind Company Name before Entity Name.
 * FR #5905 MRB: no silent edits[0] fallback.
 */
function fieldValue(editFields, wantName) {
  const rows = Array.isArray(editFields) ? editFields : [];
  const want = String(wantName || '').toUpperCase().trim();
  if (!want) return null;

  for (const row of rows) {
    if (!row || typeof row !== 'object') continue;
    const title = fieldTitle(row);
    if (title && title === want) return row;
  }

  // When looking for NAME, exact ENAME beats any fuzzy NAME hit (Company Name).
  if (want === 'NAME') {
    for (const row of rows) {
      if (!row || typeof row !== 'object') continue;
      if (fieldTitle(row) === 'ENAME') return row;
    }
  }

  // ENAME / NAME: Entity Name is the Priority title (before Company Name).
  if (want === 'NAME' || want === 'ENAME') {
    for (const row of rows) {
      if (!row || typeof row !== 'object') continue;
      const title = fieldTitle(row);
      if (title === 'ENTITY NAME' || (/\bENTITY\b/.test(title) && /\bNAME\b/.test(title))) {
        return row;
      }
    }
  }

  const esc = want.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const wordRe = new RegExp(`(?:^|[^A-Z0-9])${esc}(?:[^A-Z0-9]|$)`);
  let companyNameHit = null;
  for (const row of rows) {
    if (!row || typeof row !== 'object') continue;
    const title = fieldTitle(row);
    if (!title || !wordRe.test(` ${title} `)) continue;
    if (want === 'NAME' || want === 'ENAME') {
      if (/\bCOMPANY\b/.test(title)) {
        if (!companyNameHit) companyNameHit = row;
        continue;
      }
    }
    return row;
  }
  if (companyNameHit) return companyNameHit;
  return null;
}

async function walkProc(priority, args) {
  const errors = [];
  let ended = false;
  let nameSubmitted = false;
  const progress = () => {};
  let step = await priority.procStart(args.proc, 'P', progress, args.company);
  // Bound steps so a stuck procedure cannot hang the console forever.
  for (let i = 0; i < 40; i += 1) {
    if (!step || typeof step !== 'object') break;
    const type = String(step.type || '');
    const proc = step.proc;
    if (type === 'end' || type === 'End' || !proc) {
      ended = true;
      break;
    }
    if (type === 'inputFields') {
      const input = step.input || {};
      // SDK docs use EditField (singular) on the step; EditFields on the response payload.
      const edits = input.EditFields || input.editFields || input.EditField || input.editField || [];
      const data = { EditFields: [] };
      // FR #5916: single preferred name field (exact / ENAME / Entity Name); no broad NAME/EXEC/ENTITY sweep.
      const nameField = fieldValue(edits, 'ENAME') || fieldValue(edits, 'NAME') || null;
      // FR #5927 / MRB #5929: fail only before the name is bound. Later inputFields
      // steps without ENAME/NAME must not cancel a walk that already submitted the name.
      if (args.name && !nameField && !nameSubmitted) {
        errors.push('name_field_missing');
        try {
          if (typeof proc.cancel === 'function') {
            await proc.cancel();
          }
        } catch {
          /* ignore cancel failures on hard stop */
        }
        ended = false;
        return { ok: false, ended, errors };
      }
      if (nameField && args.name && !nameSubmitted) {
        const fieldNum = nameField.field != null ? nameField.field : 1;
        data.EditFields.push({ field: fieldNum, op: 0, value: String(args.name) });
        nameSubmitted = true;
      }
      step = await proc.inputFields(1, data);
      continue;
    }
    if (type === 'inputOptions') {
      step = await proc.inputOptions(1, 1);
      continue;
    }
    if (type === 'message') {
      // Priority Web SDK: step.message + step.messagetype; respond via proc.message(ok).
      const text = String(step.message || step.Message || (step.input && (step.input.message || step.input.Message || step.input.text)) || '');
      const severity = String(step.messagetype || step.messageType || step.severity || (step.input && (step.input.severity || step.input.Severity)) || '').toLowerCase();
      // Prefer messagetype/severity; only fall back to text /error/i when severity is absent (FR #5927).
      const isError =
        severity === 'e' ||
        severity === 'error' ||
        ((!severity || severity === '') && /error/i.test(text));
      if (isError) {
        errors.push(text || 'procedure_error');
        try {
          if (typeof proc.message === 'function') {
            step = await proc.message(0);
          } else {
            step = await proc.cancel();
          }
        } catch {
          break;
        }
        continue;
      }
      if (typeof proc.message === 'function') {
        step = await proc.message(1);
      } else if (typeof proc.continueProc === 'function') {
        step = await proc.continueProc();
      } else {
        break;
      }
      continue;
    }
    if (typeof proc.continueProc === 'function') {
      step = await proc.continueProc();
      continue;
    }
    break;
  }
  return { ok: errors.length === 0 && ended, ended, errors };
}

async function main() {
  const args = parseArgs(process.argv);
  const password = process.env.PRIORITY_SDK_PASSWORD || '';
  if (!args.name) {
    emit({ ok: false, ended: false, errors: ['name_missing'] });
    process.exitCode = 2;
    return;
  }
  if (!args.url || !args.user || !password) {
    emit({ ok: false, ended: false, errors: ['login_config_missing'] });
    process.exitCode = 2;
    return;
  }
  if (!args.company) {
    emit({ ok: false, ended: false, errors: ['company_missing'] });
    process.exitCode = 2;
    return;
  }

  let priority;
  try {
    // Prefer sibling ../node_modules (pack layout), then cwd resolution.
    const candidates = [
      path.join(__dirname, '..', 'node_modules', 'priority-web-sdk'),
      path.join(__dirname, 'node_modules', 'priority-web-sdk'),
      'priority-web-sdk',
    ];
    let lastErr;
    for (const c of candidates) {
      try {
        priority = require(c);
        lastErr = null;
        break;
      } catch (e) {
        lastErr = e;
      }
    }
    if (!priority) throw lastErr || new Error('priority-web-sdk missing');
  } catch (e) {
    emit({
      ok: false,
      ended: false,
      errors: [`sdk_require_failed:${e && e.name ? e.name : 'Error'}`],
    });
    process.exitCode = 3;
    return;
  }

  const conf = {
    username: args.user,
    password,
    url: args.url,
    tabulaini: 'tabula.ini',
    language: 3,
    company: args.company,
  };

  try {
    await priority.login(conf);
    const result = await walkProc(priority, args);
    emit(result);
    process.exitCode = result.ok ? 0 : 1;
  } catch (e) {
    emit({
      ok: false,
      ended: false,
      errors: [String((e && e.message) || e || 'sdk_walk_failed').slice(0, 200)],
    });
    process.exitCode = 1;
  } finally {
    delete process.env.PRIORITY_SDK_PASSWORD;
  }
}

const isCli = process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url));
if (isCli) {
  main();
}

export { fieldValue, walkProc, parseArgs };
