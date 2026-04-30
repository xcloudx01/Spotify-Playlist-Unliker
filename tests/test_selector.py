from __future__ import annotations

import pytest

from src.selector import parse_selection


def test_parse_selection_with_commas_and_ranges() -> None:
    assert parse_selection("1,3,5-7", 10) == [1, 3, 5, 6, 7]


def test_parse_selection_supports_plain_range() -> None:
    assert parse_selection("2-9", 10) == [2, 3, 4, 5, 6, 7, 8, 9]


def test_parse_selection_supports_explicit_csv() -> None:
    assert parse_selection("2,3,4,5", 10) == [2, 3, 4, 5]


def test_parse_selection_supports_explicit_csv_with_spaces() -> None:
    assert parse_selection("2, 3, 4, 5", 10) == [2, 3, 4, 5]


def test_parse_selection_supports_mixed_comma_and_space_separators() -> None:
    assert parse_selection("1,2,3 6-8, 10", 12) == [1, 2, 3, 6, 7, 8, 10]


def test_parse_selection_deduplicates() -> None:
    assert parse_selection("1,1,2-3,3", 5) == [1, 2, 3]


@pytest.mark.parametrize("value", ["", "0", "9", "3-1", "a", "1,b"])
def test_parse_selection_invalid(value: str) -> None:
    with pytest.raises((ValueError, TypeError)):
        parse_selection(value, 8)

