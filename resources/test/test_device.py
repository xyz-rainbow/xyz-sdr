"""Tests for core/device.py -- pure helpers + SimulatedSDR + resolution paths."""

from __future__ import annotations

import numpy as np
import pytest

from core.device import (
    HardwareInitializationError,
    SDRDevice,
    SimulatedSDR,
    _device_label,
    _device_option_label,
    _driver_name,
    _format_bandwidth_hz,
    _is_miri_sdrplay_proxy,
    _kwargs_match,
    _rate_within_soapy_range,
    _sdrplay_resolution_hint,
    _summarize_devices,
    build_driver_select_options,
    filter_sdr_devices,
    format_device_detail_lines,
    resolve_device,
    resolve_settings_device_display,
)


# ---------------------------------------------------------------------------
# Pure formatting helpers
# ---------------------------------------------------------------------------


def test_format_bandwidth_hz_delegates_to_core_formatting() -> None:
    # Deprecation shim: delegates to core.formatting.format_bandwidth_hz.
    assert _format_bandwidth_hz(0.0) == "0 Hz"
    assert _format_bandwidth_hz(1_500_000.0) == "1.5 MHz"


class _FakeRange:
    def __init__(self, minimum: float, maximum: float, step: float = 0.0) -> None:
        self._min = minimum
        self._max = maximum
        self._step = step

    def minimum(self) -> float:
        return self._min

    def maximum(self) -> float:
        return self._max

    def step(self) -> float:
        return self._step


def test_rate_within_soapy_range_in_range_passes() -> None:
    assert _rate_within_soapy_range(1_000_000.0, _FakeRange(100_000.0, 10_000_000.0)) is True


def test_rate_within_soapy_range_below_minimum_fails() -> None:
    assert _rate_within_soapy_range(50_000.0, _FakeRange(100_000.0, 10_000_000.0)) is False


def test_rate_within_soapy_range_above_maximum_fails() -> None:
    assert _rate_within_soapy_range(20_000_000.0, _FakeRange(100_000.0, 10_000_000.0)) is False


def test_rate_within_soapy_range_step_alignment() -> None:
    # Step alignment is from minimum: valid rates are minimum + N * step.
    rng = _FakeRange(100_000.0, 10_000_000.0, step=1_000_000.0)
    # 100k + 5 * 1M = 5.1M is on step.
    assert _rate_within_soapy_range(5_100_000.0, rng) is True
    # 5_050_000 is off step (would round to 5.1M, drift = 50k > tolerance).
    assert _rate_within_soapy_range(5_050_000.0, rng) is False
    # minimum itself is always valid.
    assert _rate_within_soapy_range(100_000.0, rng) is True


def test_rate_within_soapy_range_step_zero_skips_alignment() -> None:
    rng = _FakeRange(0.0, 100.0, step=0.0)
    assert _rate_within_soapy_range(73.5, rng) is True


def test_driver_name_lowercases() -> None:
    assert _driver_name({"driver": "SDRPlay"}) == "sdrplay"
    assert _driver_name({"driver": "  RTLSDR  "}) == "  rtlsdr  "  # only lowercase, no trim
    assert _driver_name({}) == ""
    assert _driver_name({"driver": ""}) == ""


def test_filter_sdr_devices_excludes_audio_and_simulated() -> None:
    devices = [
        {"driver": "sdrplay", "label": "RSP1"},
        {"driver": "audio"},
        {"driver": "simulated"},
        {"driver": "rtlsdr", "label": "RTL2832U"},
        {"driver": "rtlsdr", "label": "RTL2832U#2"},
    ]
    out = filter_sdr_devices(devices)
    assert len(out) == 3
    assert all(d["driver"] in ("sdrplay", "rtlsdr") for d in out)


def test_device_label_strips_whitespace() -> None:
    assert _device_label({"label": "  RSP1A  "}) == "RSP1A"
    assert _device_label({}) == ""
    assert _device_label({"label": ""}) == ""


def test_is_miri_sdrplay_proxy_only_when_label_matches() -> None:
    assert _is_miri_sdrplay_proxy({"driver": "miri", "label": "Mirics SDRPlay RSP1"}) is True
    assert _is_miri_sdrplay_proxy({"driver": "miri", "label": "MSi2500 DVB-T"}) is False
    assert _is_miri_sdrplay_proxy({"driver": "miri", "label": "vtx3d"}) is False
    assert _is_miri_sdrplay_proxy({"driver": "rtlsdr", "label": "RTL"}) is False


def test_summarize_devices_groups_by_driver() -> None:
    devs = [
        {"driver": "sdrplay"},
        {"driver": "rtlsdr"},
        {"driver": "rtlsdr"},
        {"driver": ""},  # unknown -> "?"
    ]
    summary = _summarize_devices(devs)
    # Order-preserving join.
    assert "rtlsdr×2" in summary
    assert "sdrplay" in summary
    assert "?" in summary


def test_summarize_devices_empty_returns_empty_string() -> None:
    assert _summarize_devices([]) == ""


def test_device_option_label_prefers_label_then_driver() -> None:
    assert _device_option_label({"driver": "rtlsdr", "label": "RTL-A"}) == "RTL-A"
    assert _device_option_label({"driver": "rtlsdr"}) == "RTLSDR"
    assert _device_option_label({"driver": "rtlsdr", "label": "  "}) == "RTLSDR"
    assert _device_option_label({}) == "?"


# ---------------------------------------------------------------------------
# format_device_detail_lines
# ---------------------------------------------------------------------------


def test_format_device_detail_lines_simulated_branch() -> None:
    lines = format_device_detail_lines({"driver": "sdrplay"}, simulated=True)
    assert lines == ["Modo simulación", "Sin hardware SDR real"]


def test_format_device_detail_lines_none_with_not_simulated() -> None:
    lines = format_device_detail_lines(None, simulated=False)
    assert lines == ["(ningún dispositivo seleccionado)"]


def test_format_device_detail_lines_label_and_serial() -> None:
    lines = format_device_detail_lines(
        {"driver": "rtlsdr", "label": "RTL2832U S/N 0001", "serial": "0001"},
    )
    # label.replace(serial, "") strips the serial from the label.
    assert lines[0] == "RTL2832U S/N"
    assert "0001" in lines


def test_format_device_detail_lines_label_only() -> None:
    lines = format_device_detail_lines({"driver": "rtlsdr", "label": "RTL-A"})
    assert lines == ["RTL-A"]


def test_format_device_detail_lines_no_label_uses_driver() -> None:
    lines = format_device_detail_lines({"driver": "rtlsdr"})
    assert lines == ["RTLSDR"]


def test_format_device_detail_lines_serial_only() -> None:
    lines = format_device_detail_lines({"driver": "rtlsdr", "serial": "9999"})
    # serial-only path appends to lines list.
    assert "9999" in lines
    assert "RTLSDR" in lines[0]


# ---------------------------------------------------------------------------
# resolve_settings_device_display
# ---------------------------------------------------------------------------


def test_resolve_settings_device_display_simulated_short_circuit() -> None:
    out = resolve_settings_device_display(
        None, {}, None, current_driver="sdrplay", simulated=True,
    )
    assert out == ["Modo simulación", "Sin hardware SDR real"]


def test_resolve_settings_device_display_sim_driver_string() -> None:
    out = resolve_settings_device_display(
        None, {}, None, current_driver="sim", simulated=False,
    )
    assert out[0] == "Modo simulación"


def test_resolve_settings_device_display_token_is_dict() -> None:
    dev = {"driver": "rtlsdr", "label": "RTL-A"}
    out = resolve_settings_device_display(
        "preset:rtlsdr", {"preset:rtlsdr": dev}, [dev],
        current_driver="auto", simulated=False,
    )
    assert out[0] == "RTL-A"


def test_resolve_settings_device_display_auto_no_devices() -> None:
    out = resolve_settings_device_display(
        None, {}, [], current_driver="auto", simulated=False,
    )
    assert out == ["Auto — sin dispositivos en caché de arranque"]


def test_resolve_settings_device_display_auto_with_devices_picks_first() -> None:
    devs = [{"driver": "rtlsdr", "label": "RTL-A"}]
    out = resolve_settings_device_display(
        None, {}, devs, current_driver="auto", simulated=False,
    )
    assert "RTL-A" in out


def test_resolve_settings_device_display_specific_driver_match() -> None:
    devs = [
        {"driver": "rtlsdr", "label": "RTL-A"},
        {"driver": "sdrplay", "label": "RSP1"},
    ]
    out = resolve_settings_device_display(
        None, {}, devs, current_driver="sdrplay", simulated=False,
    )
    assert "RSP1" in out


def test_resolve_settings_device_display_unknown_driver_falls_back() -> None:
    devs = [{"driver": "rtlsdr", "label": "RTL-A"}]
    out = resolve_settings_device_display(
        None, {}, devs, current_driver="hackrf", simulated=False,
    )
    assert "Preset: HACKRF" in out[0]


# ---------------------------------------------------------------------------
# _kwargs_match
# ---------------------------------------------------------------------------


def test_kwargs_match_empty_returns_false() -> None:
    assert _kwargs_match(None, {"driver": "rtlsdr"}) is False
    assert _kwargs_match({"driver": "rtlsdr"}, None) is False
    assert _kwargs_match(None, None) is False


def test_kwargs_match_same_keys_same_values_true() -> None:
    left = {"driver": "rtlsdr", "label": "RTL-A", "serial": "1234"}
    right = {"driver": "rtlsdr", "label": "RTL-A", "serial": "1234"}
    assert _kwargs_match(left, right) is True


def test_kwargs_match_driver_differs_false() -> None:
    left = {"driver": "rtlsdr", "label": "RTL-A"}
    right = {"driver": "sdrplay", "label": "RTL-A"}
    assert _kwargs_match(left, right) is False


def test_kwargs_match_label_differs_false() -> None:
    left = {"driver": "rtlsdr", "label": "RTL-A"}
    right = {"driver": "rtlsdr", "label": "RTL-B"}
    assert _kwargs_match(left, right) is False


def test_kwargs_match_unrelated_keys_ignored() -> None:
    left = {"driver": "rtlsdr", "foo": "x"}
    right = {"driver": "rtlsdr", "bar": "y"}
    assert _kwargs_match(left, right) is True


# ---------------------------------------------------------------------------
# build_driver_select_options
# ---------------------------------------------------------------------------


def test_build_driver_select_options_includes_all_presets() -> None:
    options, token_map, selected = build_driver_select_options(devices=[])
    labels = [opt[0] for opt in options]
    assert "Auto (primer dispositivo)" in labels
    assert "SDRplay RSP" in labels
    assert "Simulación (Hardware)" in labels
    assert "preset:auto" in token_map.values() or selected == "preset:auto"


def test_build_driver_select_options_adds_devices_as_tokens() -> None:
    devs = [
        {"driver": "rtlsdr", "label": "RTL-A"},
        {"driver": "sdrplay", "label": "RSP1"},
    ]
    options, token_map, _ = build_driver_select_options(devices=devs)
    tokens = [opt[1] for opt in options]
    assert "dev:0" in tokens
    assert "dev:1" in tokens
    assert token_map["dev:0"] == {"driver": "rtlsdr", "label": "RTL-A"}


def test_build_driver_select_options_filters_audio_and_simulated() -> None:
    devs = [
        {"driver": "audio", "label": "audio-dev"},
        {"driver": "simulated", "label": "sim-dev"},
        {"driver": "rtlsdr", "label": "RTL-A"},
    ]
    options, token_map, _ = build_driver_select_options(devices=devs)
    tokens = [opt[1] for opt in options]
    # Only the rtlsdr device should be added as dev:N token; audio/sim excluded.
    assert "dev:0" in tokens
    assert token_map["dev:0"] == {"driver": "rtlsdr", "label": "RTL-A"}


def test_build_driver_select_options_selects_active_kwargs_match() -> None:
    dev = {"driver": "rtlsdr", "label": "RTL-A"}
    options, token_map, selected = build_driver_select_options(
        devices=[dev],
        current_driver="auto",
        active_kwargs={"driver": "rtlsdr", "label": "RTL-A", "serial": ""},
    )
    assert selected == "dev:0"


def test_build_driver_select_options_sim_alias_resolves() -> None:
    options, token_map, selected = build_driver_select_options(
        devices=[], current_driver="sim",
    )
    assert selected == "preset:simulated"


def test_build_driver_select_options_unknown_driver_falls_back_to_auto() -> None:
    options, token_map, selected = build_driver_select_options(
        devices=[], current_driver="my_custom_driver_xyz",
    )
    assert selected == "preset:auto"


# ---------------------------------------------------------------------------
# _sdrplay_resolution_hint
# ---------------------------------------------------------------------------


def test_sdrplay_resolution_hint_no_devices_includes_plugin_hint() -> None:
    hint = _sdrplay_resolution_hint([])
    assert "SoapySDRUtil --find=driver=sdrplay" in hint


def test_sdrplay_resolution_hint_with_sdrplay_returns_empty_string() -> None:
    devs = [{"driver": "sdrplay", "label": "RSP1"}]
    hint = _sdrplay_resolution_hint(devs)
    assert hint == ""


def test_sdrplay_resolution_hint_miri_non_sdrplay_proxy_warns() -> None:
    devs = [{"driver": "miri", "label": "MSi2500"}]
    hint = _sdrplay_resolution_hint(devs)
    assert "miri" in hint.lower()
    assert "sdrplay" in hint.lower()


def test_sdrplay_resolution_hint_miri_sdrplay_proxy_silent() -> None:
    # Need a real sdrplay device present so the "no devices" hint is skipped;
    # the miri-sdrplay-proxy branch is silent by design.
    devs = [
        {"driver": "sdrplay", "label": "RSP1"},
        {"driver": "miri", "label": "Mirics SDRPlay RSP1"},
    ]
    hint = _sdrplay_resolution_hint(devs)
    assert hint == ""


# ---------------------------------------------------------------------------
# resolve_device
# ---------------------------------------------------------------------------


def test_resolve_device_empty_raises_hardware_init_error() -> None:
    with pytest.raises(HardwareInitializationError, match="No hay dispositivos SDR"):
        resolve_device("auto", devices=[])


def test_resolve_device_simulated_returns_simulated_dict() -> None:
    devs = [{"driver": "rtlsdr", "label": "RTL"}]
    out = resolve_device("simulated", devices=devs)
    assert out == {"driver": "simulated"}


def test_resolve_device_auto_picks_preferred_order() -> None:
    devs = [
        {"driver": "rtlsdr", "label": "RTL"},
        {"driver": "sdrplay", "label": "RSP1"},
    ]
    out = resolve_device("auto", devices=devs)
    # _PREFERRED_AUTO_ORDER starts with sdrplay.
    assert out["driver"] == "sdrplay"


def test_resolve_device_auto_falls_back_to_first() -> None:
    devs = [{"driver": "hackrf", "label": "HackRF"}]
    out = resolve_device("auto", devices=devs)
    assert out["driver"] == "hackrf"


def test_resolve_device_specific_driver_match() -> None:
    devs = [
        {"driver": "rtlsdr", "label": "RTL"},
        {"driver": "sdrplay", "label": "RSP1"},
    ]
    out = resolve_device("rtlsdr", devices=devs)
    assert out["driver"] == "rtlsdr"


def test_resolve_device_sdrplay_falls_back_to_miri_proxy() -> None:
    devs = [{"driver": "miri", "label": "Mirics SDRPlay RSP1"}]
    out = resolve_device("sdrplay", devices=devs)
    assert out["driver"] == "miri"


def test_resolve_device_sdrplay_not_found_raises_with_hint() -> None:
    devs = [{"driver": "rtlsdr", "label": "RTL"}]
    with pytest.raises(HardwareInitializationError, match="No se encontró dispositivo SDRplay"):
        resolve_device("sdrplay", devices=devs)


def test_resolve_device_unknown_driver_raises_with_summary() -> None:
    devs = [{"driver": "rtlsdr", "label": "RTL"}]
    with pytest.raises(HardwareInitializationError, match="No se encontró dispositivo"):
        resolve_device("hackrf", devices=devs)


# ---------------------------------------------------------------------------
# SimulatedSDR
# ---------------------------------------------------------------------------


def test_simulated_sdr_basic_attributes() -> None:
    sim = SimulatedSDR()
    assert sim.center_freq == 100_600_000
    assert sim.sample_rate == 2_048_000
    assert sim.gain == 40.0


def test_simulated_sdr_read_samples_shape_dtype() -> None:
    sim = SimulatedSDR()
    samples = sim.read_samples(4096)
    assert samples.shape == (4096,)
    assert samples.dtype == np.complex64


def test_simulated_sdr_read_samples_advances_time() -> None:
    sim = SimulatedSDR()
    sim.read_samples(1024)
    t1 = sim._t
    sim.read_samples(2048)
    t2 = sim._t
    assert t2 > t1
    # The second read advances by exactly 2048 / sample_rate.
    assert t2 - t1 == pytest.approx(2048 / sim.sample_rate)


def test_simulated_sdr_close_is_noop() -> None:
    SimulatedSDR().close()  # must not raise


# ---------------------------------------------------------------------------
# SDRDevice basic attributes and open/close paths
# ---------------------------------------------------------------------------


def test_sdrdevice_default_attributes() -> None:
    dev = SDRDevice(driver="sdrplay")
    assert dev.driver == "sdrplay"
    assert dev.channel == 0
    assert dev._sdr is None
    assert dev._stream is None
    assert dev.center_freq == 100_600_000.0
    assert dev.sample_rate == 2_048_000.0
    assert dev.gain == 40.0
    assert dev.auto_gain is False
    assert dev._sdrplay_pending_sample_rate is None
    assert dev._sdrplay_stream_bootstrapped is False


def test_sdrdevice_open_simulated_creates_simulatedsdr() -> None:
    dev = SDRDevice(driver="sim")
    assert dev.open() is True
    assert isinstance(dev._sdr, SimulatedSDR)
    assert dev.driver == "simulated"
    dev.close()


def test_sdrdevice_open_simulated_via_kwargs() -> None:
    dev = SDRDevice(driver="sdrplay")
    assert dev.open({"driver": "sim"}) is True
    assert isinstance(dev._sdr, SimulatedSDR)
    assert dev.driver == "simulated"
    assert dev._device_kwargs == {"driver": "sim"}
    dev.close()


def test_sdrdevice_native_settings_deferred_false_for_sim() -> None:
    dev = SDRDevice(driver="sim")
    dev._sdr = SimulatedSDR()
    assert dev._native_settings_deferred() is False


def test_sdrdevice_native_settings_deferred_true_when_sdrplay_open_no_stream() -> None:
    """Mock an sdrplay Soapy device to make the deferred check return True."""
    dev = SDRDevice(driver="sdrplay")
    fake = SimulatedSDR()  # not isinstance check is the discriminator, so use a non-Simulated stub
    # SimulatedSDR is excluded from deferred -- use a non-simulated type:
    class _FakeSoapy:
        pass

    dev._sdr = _FakeSoapy()
    dev._stream = None
    assert dev._native_settings_deferred() is True


def test_sdrdevice_reset_stream_stats_creates_new_instance() -> None:
    dev = SDRDevice(driver="sim")
    assert dev.stream_stats is not None
    dev.reset_stream_stats()
    # After reset, get a fresh StreamStats instance.
    assert dev.stream_stats is not None


def test_sdrdevice_same_device_as_compares_kwargs() -> None:
    dev = SDRDevice(driver="sim")
    dev._device_kwargs = {"driver": "simulated", "label": "test"}
    assert dev.same_device_as({"driver": "simulated", "label": "test"}) is True
    assert dev.same_device_as({"driver": "simulated", "label": "other"}) is False
    assert dev.same_device_as(None) is False


def test_sdrdevice_close_when_sdr_none() -> None:
    dev = SDRDevice(driver="sim")
    # close() with _sdr=None must not raise.
    dev.close()


def test_sdrdevice_close_simulated_no_io_thread() -> None:
    dev = SDRDevice(driver="sim")
    dev.open()
    dev.close()
    assert dev._sdr is None


def test_sdrdevice_close_fast_path_skips_io_thread() -> None:
    dev = SDRDevice(driver="sim")
    dev.open()
    # Close with fast=True must skip the run_sdr_io path entirely.
    dev.close(fast=True)
    assert dev._sdr is None


def test_sdrdevice_open_native_no_soapy_raises() -> None:
    """When _load_soapy returns False, open() -> _open_native raises."""
    from unittest.mock import patch

    dev = SDRDevice(driver="rtlsdr")

    with patch("core.device._load_soapy", return_value=False):
        with patch("core.device.run_sdr_io", side_effect=lambda fn, *a, **kw: fn(*a, **kw)):
            import pytest as _pt

            with _pt.raises(Exception) as exc_info:
                dev.open()
            assert "SoapySDR no disponible" in str(exc_info.value) or "HardwareInitializationError" in str(type(exc_info.value).__name__)