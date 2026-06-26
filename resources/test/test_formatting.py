"""Tests for core/formatting.py -- pure unit / bandwidht / Hz formatters."""

from __future__ import annotations

import pytest

from core.formatting import format_bandwidth_hz, format_hz_compact


@pytest.mark.parametrize(
    ("rate_hz", "expected"),
    [
        (0.0, "0 Hz"),
        (500.0, "500 Hz"),
        (999.0, "999 Hz"),
        (1_000.0, "1 kHz"),
        (1_500.0, "2 kHz"),  # int division for kHz branch
        (250_000.0, "250 kHz"),
        (999_999.0, "1000 kHz"),
        (1_000_000.0, "1 MHz"),
        (1_500_000.0, "1.5 MHz"),
        (2_048_000.0, "2.048 MHz"),
        (10_000_000.0, "10 MHz"),
    ],
)
def test_format_bandwidth_hz_branches(rate_hz: float, expected: str) -> None:
    assert format_bandwidth_hz(rate_hz) == expected


@pytest.mark.parametrize(
    ("hz", "expected"),
    [
        (0.0, "0Hz"),
        (500.0, "500Hz"),
        (999.0, "999Hz"),
        (1_000.0, "1k"),
        (250_000.0, "250k"),
        (999_500.0, "1000k"),
        (1_000_000.0, "1.0M"),
        (1_500_000.0, "1.5M"),
        (446_006_250.0, "446.0M"),
        (98_000_000.0, "98.0M"),
    ],
)
def test_format_hz_compact_branches(hz: float, expected: str) -> None:
    assert format_hz_compact(hz) == expected


def test_format_bandwidth_hz_trims_trailing_zeros() -> None:
    # 1_200_000 -> "1.2 MHz" (not "1.200 MHz")
    assert format_bandwidth_hz(1_200_000.0) == "1.2 MHz"


def test_format_bandwidth_hz_handles_integer_input() -> None:
    assert format_bandwidth_hz(1000) == "1 kHz"
    assert format_bandwidth_hz(0) == "0 Hz"