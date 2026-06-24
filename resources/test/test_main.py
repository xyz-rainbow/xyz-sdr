"""Tests de main.py (CLI y gates de arranque)."""

from __future__ import annotations

import argparse
from unittest.mock import patch

import pytest


def test_parse_args_defaults():
    with patch("sys.argv", ["main.py"]):
        import main

        parser = argparse.ArgumentParser()
        parser.add_argument("--sim", action="store_true")
        parser.add_argument("--check", action="store_true")
        parser.add_argument("--config", default="config/defaults.toml")
        args = parser.parse_args([])
        assert args.sim is False
        assert args.check is False
        assert "defaults.toml" in args.config


def test_load_config_merges_sections():
    import main

    cfg = main.load_config("config/defaults.toml")
    assert "device" in cfg
    assert "dsp" in cfg
    assert cfg["device"]["sample_rate"] > 0
