#!/usr/bin/env node
/**
 * FR #5905 MRB hostile: exercise walkProc with a stub Priority SDK (no network).
 * Exit 0 when JSON result matches expected; else exit 1.
 */
import { fieldValue, walkProc } from './run-repprep-via-exec.mjs';

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

function testFieldValueNoSilentFallback() {
  const noName = [
    { field: 1, title: 'COMPANY' },
    { field: 2, title: 'STATUS' },
  ];
  assert(fieldValue(noName, 'NAME') === null, 'NAME miss must be null (no silent edits[0])');
  assert(fieldValue(noName, 'ENAME') === null, 'ENAME miss must be null');
  const withEname = [
    { field: 1, title: 'COMPANY' },
    { field: 2, title: 'ENAME' },
  ];
  // FR #5916: NAME prefer exact ENAME over substring / Company Name.
  assert(fieldValue(withEname, 'ENAME') && fieldValue(withEname, 'ENAME').field === 2, 'ENAME match');
  assert(fieldValue(withEname, 'NAME') && fieldValue(withEname, 'NAME').field === 2, 'NAME prefers ENAME');
  assert(fieldValue(withEname, 'COMPANY').field === 1, 'exact title match');
}

/** FR #5916: Company Name must not win over Entity Name for want=NAME. */
function testCompanyNameBeforeEntityName() {
  const edits = [
    { field: 1, title: 'Company Name' },
    { field: 2, title: 'Entity Name' },
  ];
  const hit = fieldValue(edits, 'NAME');
  assert(hit && hit.field === 2, 'Entity Name preferred over earlier Company Name');
  assert(fieldValue(edits, 'ENAME') && fieldValue(edits, 'ENAME').field === 2, 'ENAME binds Entity Name');
  const exactName = [
    { field: 1, title: 'Company Name' },
    { field: 9, title: 'NAME' },
  ];
  assert(fieldValue(exactName, 'NAME').field === 9, 'exact NAME beats Company Name');
}

async function testWalkInputAndMessage() {
  const calls = [];
  const proc = {
    async inputFields(ok, data) {
      calls.push({ kind: 'inputFields', ok, data });
      return {
        type: 'message',
        message: 'ready',
        messagetype: 'information',
        proc,
      };
    },
    async message(ok) {
      calls.push({ kind: 'message', ok });
      return { type: 'end', proc: null };
    },
    async cancel() {
      calls.push({ kind: 'cancel' });
      return { type: 'end', proc: null };
    },
    async continueProc() {
      calls.push({ kind: 'continueProc' });
      throw new Error('continueProc must not handle message steps');
    },
  };
  const priority = {
    async procStart(name) {
      calls.push({ kind: 'procStart', name });
      return {
        type: 'inputFields',
        proc,
        input: {
          EditField: [
            { field: 9, title: 'OTHER' },
            { field: 1, title: 'Company Name' },
            { field: 3, title: 'Entity Name' },
          ],
        },
      };
    },
  };
  const result = await walkProc(priority, {
    name: 'CUSTOMERS',
    company: 'c',
    proc: 'REPPREPDIRECT2',
  });
  assert(result.ok === true, `expected ok, got ${JSON.stringify(result)}`);
  assert(result.ended === true, 'ended');
  const inp = calls.find((c) => c.kind === 'inputFields');
  assert(inp, 'inputFields called');
  assert(inp.data.EditFields.some((e) => e.field === 3 && e.value === 'CUSTOMERS'), 'ENAME field filled');
  assert(!inp.data.EditFields.some((e) => e.field === 9), 'must not fill OTHER via silent fallback');
  assert(!inp.data.EditFields.some((e) => e.field === 1), 'must not fill Company Name (FR #5916)');
  assert(inp.data.EditFields.length === 1, 'only Entity Name filled (no broad NAME/EXEC/ENTITY sweep)');
  assert(calls.some((c) => c.kind === 'message' && c.ok === 1), 'message(1) for info');
  assert(!calls.some((c) => c.kind === 'continueProc'), 'no continueProc on message');
}

async function testWalkErrorMessage() {
  const calls = [];
  const proc = {
    async message(ok) {
      calls.push({ kind: 'message', ok });
      return { type: 'end', proc: null };
    },
    async cancel() {
      calls.push({ kind: 'cancel' });
      return { type: 'end', proc: null };
    },
  };
  const priority = {
    async procStart() {
      return {
        type: 'message',
        message: 'boom',
        messagetype: 'error',
        proc,
      };
    },
  };
  const result = await walkProc(priority, {
    name: 'CUSTOMERS',
    company: 'c',
    proc: 'REPPREPDIRECT2',
  });
  assert(result.ok === false, 'error message => not ok');
  assert((result.errors || []).includes('boom'), 'error text collected');
  assert(calls.some((c) => c.kind === 'message' && c.ok === 0), 'message(0) on error');
}

/** FR #5927: informational messagetype must not be treated as error just because text says "No errors". */
async function testWalkInfoMessageWithErrorWord() {
  const calls = [];
  const proc = {
    async message(ok) {
      calls.push({ kind: 'message', ok });
      return { type: 'end', proc: null };
    },
  };
  const priority = {
    async procStart() {
      return {
        type: 'message',
        message: 'No errors',
        messagetype: 'information',
        proc,
      };
    },
  };
  const result = await walkProc(priority, {
    name: 'CUSTOMERS',
    company: 'c',
    proc: 'REPPREPDIRECT2',
  });
  assert(result.ok === true, 'information + "No errors" text must stay ok');
  assert(calls.some((c) => c.kind === 'message' && c.ok === 1), 'message(1) for information');
}

/** FR #5927: when args.name is set but no ENAME/NAME field binds, fail (do not submit empty EditFields). */
async function testWalkNameFieldMissing() {
  const calls = [];
  const proc = {
    async inputFields(ok, data) {
      calls.push({ kind: 'inputFields', ok, data });
      return { type: 'end', proc: null };
    },
    async cancel() {
      calls.push({ kind: 'cancel' });
      return { type: 'end', proc: null };
    },
  };
  const priority = {
    async procStart() {
      return {
        type: 'inputFields',
        proc,
        input: {
          EditField: [
            { field: 1, title: 'STATUS' },
            { field: 2, title: 'OTHER' },
          ],
        },
      };
    },
  };
  const result = await walkProc(priority, {
    name: 'CUSTOMERS',
    company: 'c',
    proc: 'REPPREPDIRECT2',
  });
  assert(result.ok === false, 'name field miss => not ok');
  assert((result.errors || []).includes('name_field_missing'), 'name_field_missing error');
  assert(!calls.some((c) => c.kind === 'inputFields'), 'must not call inputFields with empty EditFields');
}

async function main() {
  testFieldValueNoSilentFallback();
  testCompanyNameBeforeEntityName();
  await testWalkInputAndMessage();
  await testWalkErrorMessage();
  await testWalkInfoMessageWithErrorWord();
  await testWalkNameFieldMissing();
  process.stdout.write(JSON.stringify({ ok: true, selftest: 'walk' }) + '\n');
}

main().catch((e) => {
  process.stderr.write(String(e && e.stack ? e.stack : e) + '\n');
  process.exitCode = 1;
});
