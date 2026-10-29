"""Short-lived caller helper for authenticated Airc DCC uploads."""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from pathlib import Path

import airc_dcc_bulk as dcc
from airc_jobs import MAX_PUT_BYTES


def _route_address() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 9))
        address = str(sock.getsockname()[0])
        if address and not address.startswith("127."):
            return address
    finally:
        sock.close()
    for address in socket.gethostbyname_ex(socket.gethostname())[2]:
        if address and not address.startswith("127."):
            return address
    raise OSError("no non-loopback upload address; pass --advertise-host")


def _write_offer(path: Path, offer: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(offer), encoding="utf-8")
    os.replace(temp, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--offer-file", required=True)
    parser.add_argument("--advertise-host", default="")
    parser.add_argument("--bind-host", default="")
    parser.add_argument("--relay", default="")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)

    source = Path(args.file)
    offer_path = Path(args.offer_file)
    try:
        payload = source.read_bytes()
        if len(payload) > MAX_PUT_BYTES:
            raise ValueError(f"upload exceeds {MAX_PUT_BYTES} byte PUT limit")
        digest = dcc.sha256_hex(payload)
        token = dcc.make_dcc_token()
        if args.relay:
            relay_host, sep, relay_port = args.relay.rpartition(":")
            if not sep or not relay_host or not relay_port or not relay_port.isdigit():
                raise ValueError("relay must be host:port")
            offer = {
                "host": "127.0.0.1",
                "port": 1,
                "token": token,
                "tls": True,
                "relay": args.relay,
                "bytes": len(payload),
                "sha256": digest,
            }
            _write_offer(offer_path, offer)
            dcc.reverse_dcc_send_via_relay(
                payload,
                relay_host=relay_host,
                relay_port=int(relay_port),
                token=token,
                timeout_s=args.timeout,
            )
        else:
            advertise_host = args.advertise_host
            if args.bind_host:
                bind_host = args.bind_host
            elif advertise_host in {"127.0.0.1", "::1", "localhost"}:
                bind_host = "127.0.0.1"
            else:
                bind_host = _route_address()
            advertise_host = advertise_host or bind_host

            def publish(port: int) -> None:
                _write_offer(
                    offer_path,
                    {
                        "host": advertise_host,
                        "port": port,
                        "token": token,
                        "tls": True,
                        "relay": "",
                        "bytes": len(payload),
                        "sha256": digest,
                    },
                )

            dcc.listen_and_send(
                payload,
                token=token,
                on_listening=publish,
                host=bind_host,
                timeout_s=args.timeout,
                tls=True,
            )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"DCC upload unavailable: {type(exc).__name__}", file=sys.stderr)
        return 1
    finally:
        for path in (offer_path.with_name(offer_path.name + ".tmp"),):
            try:
                path.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
