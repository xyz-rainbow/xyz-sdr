"""Tests de selección AUTO de modo de demodulación."""

from __future__ import annotations

from core.auto_demod import resolve_auto_demod_mode


def test_auto_fm_broadcast():
    assert resolve_auto_demod_mode(98.0e6) == "wbfm"


def test_auto_airband_nbfm():
    assert resolve_auto_demod_mode(121.5e6) == "nbfm"


def test_auto_hf_lsb():
    assert resolve_auto_demod_mode(7.1e6) == "lsb"


def test_auto_hf_usb():
    assert resolve_auto_demod_mode(14.2e6) == "usb"


def test_auto_pmr():
    assert resolve_auto_demod_mode(446.00625e6) == "nbfm"
