'use strict';

/**
 * docs/mrb-4290: hostile pin for enable-provider stale-tip harvest lesson.
 */

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const SKILL = path.join(
  __dirname,
  '..',
  '.grok',
  'skills',
  'harvest',
  'SKILL.md',
);

const LESSON =
  'Enable-provider FR when stale tip is far behind main: implement fresh from origin/main, open successor Closes PR, close old tip with Duplicate of #N / fixed by PR #M; scrub STILL_DARK/DISABLED_LOCAL/floors (N enabled x 2) and hardcoded dark-of-webgains samples in sibling enable tests';

describe('docs/mrb-4290 hostile enable-provider stale-tip lesson', () => {
  it('SKILL.md pins enable-provider stale tip successor contiguous', () => {
    const buf = fs.readFileSync(SKILL);
    assert.notEqual(buf[0], 0xef, 'no BOM');
    const text = buf.toString('utf8');
    assert.match(text, new RegExp(LESSON.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
    const line = text.split(/\r?\n/).find((l) => l.includes('Enable-provider FR when stale tip'));
    assert.ok(line, 'lesson line present');
    assert.equal(line.includes('\u2014'), false, 'new lesson has no em-dash');
    assert.equal(line.includes('\u2013'), false, 'new lesson has no en-dash');
  });
});
