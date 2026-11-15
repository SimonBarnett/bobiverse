"""MRB #7573 hostile pins for FR #7570 shared fleet-pool-stale state."""
from __future__ import annotations

from pathlib import Path

import bobreport
import fleet_pool_fetch as fp

NOW = 1_700_000_100.0


def _home(tmp: Path) -> Path:
    home = tmp / 'home'
    home.mkdir()
    bobreport.save_digest(home, bobreport.empty_digest())
    return home


def test_mrb7573_after_grace_no_token_is_skipped_auth_not_filed(tmp_path: Path, monkeypatch):
    home = _home(tmp_path)
    filed: list[dict] = []
    monkeypatch.setattr(
        fp,
        'file_fleet_pool_stale_exception',
        lambda **kw: filed.append(dict(kw)) or {'ok': True, 'number': 3},
    )
    first = NOW - 120
    fp._save_state(
        home,
        {
            fp.POOL_COPILOT: {
                'first_attempt': first,
                'last_attempt': first + 10,
                'last_ok': 0.0,
                'error': 'no_token',
            }
        },
    )
    out = fp.maybe_report_fleet_pool_staleness(home, now=NOW)
    assert out[fp.POOL_COPILOT]['action'] == 'skipped-auth'
    assert filed == []


def test_mrb7573_fresh_last_ok_wins_over_digest_no_token_noise(tmp_path: Path, monkeypatch):
    """Fresh shared last_ok always wins --- digest no_token noise must not divert to skipped-auth."""
    home = _home(tmp_path)
    filed: list[dict] = []
    monkeypatch.setattr(
        fp,
        'file_fleet_pool_stale_exception',
        lambda **kw: filed.append(dict(kw)) or {'ok': True, 'number': 4},
    )
    fp._save_state(
        home,
        {
            fp.POOL_COPILOT: {
                'last_ok': NOW,
                'last_attempt': NOW,
                'first_attempt': NOW - 600,
                'error': None,
                'fail_streak': 0,
            }
        },
    )
    doc = bobreport.load_digest(home)
    doc['fleet_pools'] = {
        fp.POOL_COPILOT: {
            'id': fp.POOL_COPILOT,
            'error': 'no_token',
            'fetched_at': None,
            'remaining': None,
        }
    }
    bobreport.save_digest(home, doc)
    out = fp.maybe_report_fleet_pool_staleness(home, now=NOW + 10)
    assert out[fp.POOL_COPILOT]['action'] == 'ok'
    assert filed == []


def test_mrb7573_stale_body_quotes_last_ok_not_none(tmp_path: Path, monkeypatch):
    home = _home(tmp_path)
    filed: list[dict] = []
    monkeypatch.setattr(
        fp,
        'file_fleet_pool_stale_exception',
        lambda **kw: filed.append(dict(kw)) or {'ok': True, 'number': 5, 'deduped': False},
    )
    monkeypatch.setattr(fp, 'comment_fleet_pool_stale_issue', lambda **k: True)
    last_ok = NOW - 200
    fp._save_state(
        home,
        {
            fp.POOL_OC_GO: {
                'last_ok': last_ok,
                'last_attempt': last_ok + 5,
                'first_attempt': last_ok - 1000,
                'error': 'provider-timeout',
                'fail_streak': 3,
            }
        },
    )
    doc = bobreport.load_digest(home)
    doc['fleet_pools'] = {
        fp.POOL_OC_GO: {
            'id': fp.POOL_OC_GO,
            'fetched_at': '2026-11-15T16:00:00Z',
            'remaining': 55,
            'error': 'provider-timeout',
        }
    }
    bobreport.save_digest(home, doc)
    out = fp.maybe_report_fleet_pool_staleness(home, now=NOW)
    assert out[fp.POOL_OC_GO]['action'] == 'filed'
    body = filed[0]['body'].lower()
    assert 'last_ok:' in body
    assert 'last_ok: (none)' not in body and 'last_ok: (none)' not in body
    assert 'provider-timeout' in body
