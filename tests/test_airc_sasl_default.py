"""Reserved {machine}_console needs SASL before NICK (fleet Ergo)."""

from airc_console_service import build_arg_parser


def test_sasl_defaults_on():
    args = build_arg_parser().parse_args([])
    assert args.sasl is True


def test_no_sasl_flag():
    args = build_arg_parser().parse_args(["--no-sasl"])
    assert args.sasl is False
