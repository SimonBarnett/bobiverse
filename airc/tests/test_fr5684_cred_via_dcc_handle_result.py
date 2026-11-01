"""FR #5684: CRED via=dcc must return HandleResult(action='cred'), never TypeError.

Live MarchHare: HandleResult(True, reply, action='cred') crashed with
'multiple values for argument action', so no out/err/DONE reached IRC and
passed credentials were never staged (FR #5659 unusable).
"""
from __future__ import annotations

import json

import airc_console as ac
import airc_dcc_bulk as dcc
import airc_passed_cred as pcred
from airc_auth_helpers import ops_auth

FAKE_PW = "FAKE_" + "5684_cred_pw"
FAKE_USER = "WONDERLAND\\airc-retest-dummy"
QID = "c5659002"


class _OfferRunner:
    def __init__(self, offer):
        self._offer = offer
        self.taken: list[str] = []

    def take_dcclisten(self, qid):
        self.taken.append(qid)
        return self._offer


def _core(runner=None, store=None):
    auth = ops_auth("op", channel="#tm")
    core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        nick="tm_console",
        shell_runner=runner,
    )
    if store is not None:
        core.passed_cred_store = store
    return core


def _offer(qid=QID):
    return dcc.DccListenOffer(
        job_id=qid,
        host="127.0.0.1",
        port=9,
        token="ab" * 16,
        tls=True,
    )


def test_fr5684_cred_success_stages_and_replies(monkeypatch):
    store = pcred.PassedCredStore()
    runner = _OfferRunner(_offer())
    payload = json.dumps({"username": FAKE_USER, "password": FAKE_PW}).encode("utf-8")

    def fake_recv(offer, **kwargs):
        assert offer.job_id == QID
        return payload, "deadbeef"

    monkeypatch.setattr(dcc, "receive_upload_from_offer", fake_recv)
    # Guard: the broken tip name must not be required.
    if hasattr(dcc, "recv_offer_payload"):
        monkeypatch.delattr(dcc, "recv_offer_payload", raising=False)

    core = _core(runner=runner, store=store)
    hr = core.handle_raw(
        f":op!u@h PRIVMSG tm_console :id={QID} CRED id={QID} via=dcc"
    )
    assert hr is not None
    assert hr.action == "cred"
    text = hr.reply or ""
    assert f"out id={QID} seq=1 CRED staged identity=passed" in text
    assert f"DONE id={QID} exit=0 cred-staged account={FAKE_USER}" in text
    assert FAKE_PW not in text
    assert runner.taken == [QID]
    peeked = store.peek(QID)
    assert peeked is not None
    assert peeked["username"] == FAKE_USER
    assert peeked["password"] == FAKE_PW


def test_fr5684_cred_dcc_failure_returns_err_not_typeerror(monkeypatch):
    store = pcred.PassedCredStore()
    runner = _OfferRunner(_offer())

    def boom(offer, **kwargs):
        raise OSError("dcc-down")

    monkeypatch.setattr(dcc, "receive_upload_from_offer", boom)
    core = _core(runner=runner, store=store)
    hr = core.handle_raw(
        f":op!u@h PRIVMSG tm_console :id={QID} CRED id={QID} via=dcc"
    )
    assert hr is not None
    assert hr.action == "cred"
    text = hr.reply or ""
    assert f"err id={QID} seq=1 cred failed:" in text
    assert f"DONE id={QID} exit=1 auth_failed" in text
    assert store.peek(QID) is None


def test_fr5684_cred_handle_result_kwargs_only():
    """Positional True/reply must not bind action (dataclass field 0)."""
    hr = ac.HandleResult(
        action="cred",
        nick="op",
        target="tm_console",
        text="CRED",
        reply=f"DONE id={QID} exit=0 cred-staged account=u",
    )
    assert hr.action == "cred"
    assert hr.reply and "cred-staged" in hr.reply
