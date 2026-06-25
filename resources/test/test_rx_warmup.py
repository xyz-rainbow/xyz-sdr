"""Tests de warmup RX (chunk limitado al iniciar stream)."""

from __future__ import annotations

from core.rx_warmup import RX_WARMUP_ITERS, RX_WARMUP_SAMPLE_CAP, cap_rx_warmup_samples


def test_cap_rx_warmup_limits_first_iters():
    remaining = RX_WARMUP_ITERS
    capped, remaining = cap_rx_warmup_samples(500_000, remaining)
    assert capped == 4_096
    assert remaining == RX_WARMUP_ITERS - 1


def test_cap_rx_warmup_mid_tier():
    remaining = RX_WARMUP_ITERS - 3
    capped, _ = cap_rx_warmup_samples(500_000, remaining)
    assert capped == 16_384


def test_cap_rx_warmup_passes_through_after_warmup():
    capped, remaining = cap_rx_warmup_samples(500_000, 0)
    assert capped == 500_000
    assert remaining == 0


def test_cap_rx_warmup_exhausts_counter():
    remaining = 2
    for _ in range(2):
        _, remaining = cap_rx_warmup_samples(1_000_000, remaining)
    assert remaining == 0
