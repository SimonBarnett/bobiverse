'use strict';
const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const SKILL = path.join(__dirname, '..', 'common', '.grok', 'skills', 'harvest', 'SKILL.md');
describe('docs/mrb-4290 hostile enable-provider stale-tip lesson', () => {
  it('SKILL.md pins enable-provider stale tip successor contiguous', () => {
    const buf = fs.readFileSync(SKILL);
    assert.notEqual(buf[0], 0xef, 'no BOM');
    const text = buf.toString('utf8');
    assert.equal(text.includes('\u2014'), false, 'no em-dash');
    assert.equal(text.includes('\u2013'), false, 'no en-dash');
    assert.match(
      text,
      /Enable-provider FR when stale tip is far behind main: implement fresh from origin\/main, open successor Closes PR, close old tip with Duplicate of #N \/ fixed by PR #M; scrub STILL_DARK\/DISABLED_LOCAL\/floors \(N enabled x 2\) and hardcoded dark-of-webgains samples in sibling enable tests/,
    );
  });
});
