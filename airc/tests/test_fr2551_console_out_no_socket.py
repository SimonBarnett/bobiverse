# FR #2551: background shell/job emit must not crash when IRC socket is gone.
from __future__ import annotations

import airc_console as ac
import airc_console_service as svc
import airc_jobs as aj


def test_on_console_out_swallows_no_socket_and_forces_reconnect(tmp_path, monkeypatch):
    monkeypatch.setenv('AGENTIC_IRC_PASSWORD', 'x-server-pass')
    args = svc.build_arg_parser().parse_args(
        ['--machine', 'tm', '--home', str(tmp_path), '--shop-mode', 'registered', '--operators', 'op']
    )
    s = svc.AircConsoleService(args)
    s.sock = None
    s._force_reconnect = False
    # Must not raise ConnectionError into the caller thread (crash hook path).
    s._on_console_out('bob-tm', 'out id=deadbeef seq=1 hello')
    assert s._force_reconnect is True


def test_on_console_out_swallows_send_failed_oserror(tmp_path, monkeypatch):
    monkeypatch.setenv('AGENTIC_IRC_PASSWORD', 'x-server-pass')
    args = svc.build_arg_parser().parse_args(
        ['--machine', 'tm', '--home', str(tmp_path), '--shop-mode', 'registered', '--operators', 'op']
    )
    s = svc.AircConsoleService(args)

    class _DeadSock:
        def sendall(self, data):  # noqa: ANN001
            raise OSError(10054, 'connection reset')

    s.sock = _DeadSock()
    s._force_reconnect = False
    s._on_console_out('bob-tm', 'DONE id=deadbeef exit=0')
    assert s._force_reconnect is True


def test_shell_emit_swallows_connection_error():
    def boom(nick: str, line: str) -> None:
        raise ConnectionError('send: no socket')

    runner = ac.ShellJobRunner(on_reply=boom, wait=False)
    # Direct emit must not raise into worker threads.
    runner._emit('bob-tm', 'out id=abcd1234 seq=1 hi')


def test_jobs_emit_swallows_connection_error(tmp_path):
    def boom(nick: str, line: str) -> None:
        raise ConnectionError('send: no socket')

    store = aj.JobStore(tmp_path / 'jobs')
    handler = aj.JobProtocol(store=store, on_reply=boom, machine='tm')
    handler._emit('bob-tm', 'DONE id=abcd1234 exit=0')
