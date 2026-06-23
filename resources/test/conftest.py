"""Fixtures compartidas para tests de xyz-sdr."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.runtime_paths import configure_pycache_prefix

configure_pycache_prefix(ROOT)

import numpy as np
import pytest


def pytest_configure(config) -> None:
    basetemp = ROOT / "var" / "pytest-tmp"
    basetemp.mkdir(parents=True, exist_ok=True)
    config.option.basetemp = str(basetemp)


@pytest.fixture
def center_hz() -> float:
    return 100_600_000.0


@pytest.fixture
def sample_rate() -> float:
    return 500_000.0


@pytest.fixture
def band_cols_count() -> int:
    return 512


@pytest.fixture
def synthetic_psd() -> np.ndarray:
    rng = np.random.default_rng(42)
    psd = rng.normal(loc=-60.0, scale=5.0, size=4096)
    psd[2048] = -20.0  # pico central
    return psd


@pytest.fixture
def flat_band_cols(band_cols_count: int) -> np.ndarray:
    cols = np.linspace(-80.0, -20.0, band_cols_count, dtype=np.float32)
    return cols
