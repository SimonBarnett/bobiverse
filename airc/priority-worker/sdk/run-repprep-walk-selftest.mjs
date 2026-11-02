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
  assert(fieldValue(withEname, 'ENAME') && fieldValue(withEname, 'ENAME').field === 2, 'ENAME match');
  assert(fieldValue(withEname, 'COMPANY').field === 1, 'exact title match');
  // Substring must not bind Company Name when want is NAME (MRB #5914).
  const companyBeforeEntity = [
    { field: 1, title: 'Company Name' },
    { field: 2, title: 'Entity Name' },
  ];
  assert(fieldValue(companyBeforeEntity, 'NAME') === null, 'NAME must not substring-match Company Name');
  assert(fieldValue(companyBeforeEntity, 'ENTITY NAME').field === 2, 'ENTITY NAME exact');
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
  assert(inp.data.EditFields.some((e) => e.field === 3 && e.value === 'CUSTOMERS'), 'Entity Name field filled');
  assert(!inp.data.EditFields.some((e) => e.field === 9), 'must not fill OTHER via silent fallback');
  assert(inp.data.EditFields.length === 1, 'only entity name field written');
  assert(calls.some((c) => c.kind === 'message' && c.ok === 1), 'message(1) for info');
  assert(!calls.some((c) => c.kind === 'continueProc'), 'no continueProc on message');
}

async function testWalkPrefersEntityOverCompanyName() {
  const calls = [];
  const proc = {
    async inputFields(ok, data) {
      calls.push({ kind: 'inputFields', data });
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
            { field: 1, title: 'Company Name' },
            { field: 2, title: 'Entity Name' },
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
  assert(result.ok === true && result.ended === true, 'walk ok');
  const inp = calls.find((c) => c.kind === 'inputFields');
  assert(inp, 'inputFields');
  assert(inp.data.EditFields.some((e) => e.field === 2 && e.value === 'CUSTOMERS'), 'Entity Name only');
  assert(!inp.data.EditFields.some((e) => e.field === 1), 'must not write Company Name');
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

async function main() {
  testFieldValueNoSilentFallback();
  await testWalkInputAndMessage();
  await testWalkPrefersEntityOverCompanyName();
  await testWalkErrorMessage();
  process.stdout.write(JSON.stringify({ ok: true, selftest: 'walk' }) + '\n');
}

main().catch((e) => {
  process.stderr.write(String(e && e.stack ? e.stack : e) + '\n');
  process.exitCode = 1;
});
