from __future__ import annotations

import pytest

from src.main import build_parser


def test_build_parser_has_no_execute_flag() -> None:
    args = build_parser().parse_args([])
    assert not hasattr(args, "execute")


def test_build_parser_rejects_execute_flag() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--execute"])

