"""FR #3286: AuthPolicy must not allow arbitrary bob-* nicks before operator/account checks."""
from __future__ import annotations

import inspect
import re
from pathlib import Path

import airc_console as ac


def test_bob_evil_denied_when_require_account_even_without_account():
    policy = ac.AuthPolicy(operators={"simon"}, require_account=True)
    assert policy.allow("bob-evil", account=None) is False


def test_bob_evil_with_matching_looking_account_still_denied_if_not_operator():
    policy = ac.AuthPolicy(operators={"simon"}, require_account=True)
    assert policy.allow("bob-evil", account="bob-evil") is False


def test_bob_machine_requires_account_when_require_account():
    mid = "marchhare"
    policy = ac.AuthPolicy(
        operators={"simon"},
        accounts={f"bob-{mid}"},
        require_account=True,
        machine=mid,
    )
    assert policy.allow(f"bob-{mid}", account=None) is False
    assert policy.allow(f"bob-{mid}", account=f"bob-{mid}") is True
    # Wrong account for the fleet nick
    assert policy.allow(f"bob-{mid}", account="someone-else") is False


def test_listed_operator_needs_matching_account_when_require_account():
    policy = ac.AuthPolicy(
        operators={"simon"},
        accounts={"simon"},
        require_account=True,
    )
    assert policy.allow("simon", account="simon") is True
    assert policy.allow("simon", account=None) is False
    assert policy.allow("simon", account="wrong") is False


def test_bob_fleet_nick_without_require_account_still_needs_operator_membership():
    """Even with require_account=False, nick pattern alone must not grant shell."""
    policy = ac.AuthPolicy(operators={"simon"}, machine="tm")
    assert policy.allow("bob-evil", account=None) is False
    # bob-tm is auto-added via machine= into operators
    assert policy.allow("bob-tm", account=None) is True


def test_allow_source_has_no_early_bob_regex_true_return():
    """Regression: no code path may return True from bob-* regex before ops/account checks."""
    src = inspect.getsource(ac.AuthPolicy.allow)
    # Early-return True after is_bob_fleet_nick must be gone.
    assert not re.search(
        r"if\s+is_bob_fleet_nick\s*\([^)]*\)\s*:\s*\n\s*return\s+True",
        src,
    ), "AuthPolicy.allow still short-circuits True for bob-* nicks"


def test_module_source_allow_block_orders_ops_before_bob_bypass():
    """Whole-file pin: AuthPolicy.allow body must not grant by nick regex first."""
    path = Path(ac.__file__).resolve()
    text = path.read_text(encoding="utf-8")
    # Find the allow method body roughly
    m = re.search(
        r"def allow\(self, nick: str, account: str \| None = None\) -> bool:(.*?)(?=\n    def |\n@dataclass|\nclass )",
        text,
        re.S,
    )
    assert m, "could not locate AuthPolicy.allow in source"
    body = m.group(1)
    assert "return True" not in body.split("ops =")[0] or "is_bob_fleet_nick" not in body.split("ops =")[0]
    # Stronger: is_bob_fleet_nick must not appear before ops assignment inside allow
    before_ops = body.split("ops =", 1)[0]
    assert "is_bob_fleet_nick" not in before_ops
