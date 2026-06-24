"""Tests del helper RLE del espectro."""

from __future__ import annotations

from rich.text import Text

from tui.widgets.spectrum_graph import _append_rle_runs


def test_append_rle_runs_merges_same_style():
    line = Text()
    _append_rle_runs(line, [" ", " ", "█", "█"], [None, None, "on #112233", "on #112233"])

    expected = Text()
    expected.append("  ")
    expected.append("██", "on #112233")

    assert str(line) == str(expected)
    assert line._spans == expected._spans
