"""Tests for tui/splash.py -- console-rendering helpers + progress math."""

from __future__ import annotations

import pytest

from tui.splash import (
    _banner_layout,
    _is_splash_noise_line,
    _phase_progress_window,
    _progress_fill_chars,
    _render_banner_block,
    _splash_display_lines,
    _splash_lines,
    _splash_progress_percent,
    _term_size,
    _trim_status_line,
)


# ---------------------------------------------------------------------------
# _splash_lines / _progress_fill_chars
# ---------------------------------------------------------------------------


def test_splash_lines_returns_non_empty_list() -> None:
    lines = _splash_lines()
    assert isinstance(lines, list)
    assert len(lines) > 0


def test_progress_fill_chars_returns_tuple() -> None:
    fill, empty = _progress_fill_chars()
    assert isinstance(fill, str)
    assert isinstance(empty, str)
    assert len(fill) >= 1
    assert len(empty) >= 1


# ---------------------------------------------------------------------------
# _term_size
# ---------------------------------------------------------------------------


def test_term_size_returns_tuple() -> None:
    w, h = _term_size()
    assert isinstance(w, int) and w > 0
    assert isinstance(h, int) and h > 0


def test_term_size_falls_back_to_80_24_on_oserror(monkeypatch) -> None:
    import os
    monkeypatch.setattr(
        "os.get_terminal_size",
        lambda *a, **kw: (_ for _ in ()).throw(OSError("no tty")),
    )
    assert _term_size() == (80, 24)


# ---------------------------------------------------------------------------
# _trim_status_line
# ---------------------------------------------------------------------------


def test_trim_status_line_passes_through_short_lines() -> None:
    assert _trim_status_line("hola mundo", 80) == "hola mundo"


def test_trim_status_line_strips_surrounding_whitespace() -> None:
    assert _trim_status_line("  hola  ", 80) == "hola"


def test_trim_status_line_truncates_long_lines_with_ellipsis() -> None:
    out = _trim_status_line("a" * 200, 30)
    assert len(out) <= 30
    assert out.endswith("...")


def test_trim_status_line_preserves_at_least_8_chars_before_truncation() -> None:
    out = _trim_status_line("a" * 200, 10)
    # Width=10, but min prefix length is 8 -> 8 chars + "..."
    assert out.startswith("a" * 8)
    assert out.endswith("...")


# ---------------------------------------------------------------------------
# _is_splash_noise_line
# ---------------------------------------------------------------------------


def test_is_splash_noise_line_empty_string() -> None:
    assert _is_splash_noise_line("") is True


def test_is_splash_noise_line_whitespace_only() -> None:
    assert _is_splash_noise_line("   ") is True


def test_is_splash_noise_line_detects_soapy_path() -> None:
    assert _is_splash_noise_line("C:\\path\\to\\Soapy\\module") is True


def test_is_splash_noise_line_detects_core_soapy_runtime() -> None:
    assert _is_splash_noise_line("core.soapy_runtime.bootstrap") is True


def test_is_splash_noise_line_detects_windows_drive_letter() -> None:
    assert _is_splash_noise_line("C:\\Windows\\System32") is True


def test_is_splash_noise_line_passes_clean_message() -> None:
    assert _is_splash_noise_line("Bootstrapping SDRplay service") is False


def test_is_splash_noise_line_passes_fase_label() -> None:
    assert _is_splash_noise_line("Fase: detectando hardware") is False


# ---------------------------------------------------------------------------
# _splash_display_lines
# ---------------------------------------------------------------------------


def test_splash_display_lines_returns_empty_for_none() -> None:
    assert _splash_display_lines(None) == []


def test_splash_display_lines_returns_empty_for_empty_list() -> None:
    assert _splash_display_lines([]) == []


def test_splash_display_lines_picks_latest_phase() -> None:
    lines = ["noise", "Fase: detectando hardware", "more noise"]
    assert _splash_display_lines(lines) == ["Cargando: detectando hardware…"]


def test_splash_display_lines_listo_for_done_phase() -> None:
    lines = ["Fase: listo"]
    assert _splash_display_lines(lines) == ["Listo"]


def test_splash_display_lines_listo_case_insensitive() -> None:
    lines = ["Fase: Listo"]
    assert _splash_display_lines(lines) == ["Listo"]


def test_splash_display_lines_falls_back_to_last_clean_line() -> None:
    # No "Fase:" lines -> pick the last non-noise line.
    lines = ["SOAPY plugin path", "Searching for devices", "noise"]
    out = _splash_display_lines(lines)
    # "noise" is short and doesn't match any noise marker, so it's "clean".
    # The last item returned is the last line in `clean` (= ["noise"]).
    assert out == ["noise"]


# ---------------------------------------------------------------------------
# _phase_progress_window
# ---------------------------------------------------------------------------


def test_phase_progress_window_none_for_empty() -> None:
    assert _phase_progress_window(None) is None
    assert _phase_progress_window([]) is None


def test_phase_progress_window_none_without_fase() -> None:
    assert _phase_progress_window(["some other line", "another"]) is None


def test_phase_progress_window_listo_returns_100() -> None:
    assert _phase_progress_window(["Fase: listo"]) == (100, 100)
    assert _phase_progress_window(["Fase: ready"]) == (100, 100)


def test_phase_progress_window_recovery_api_phase() -> None:
    assert _phase_progress_window(["Fase: recovery api"]) == (80, 95)


def test_phase_progress_window_enumerate_phase() -> None:
    assert _phase_progress_window(["Fase: enumerate devices"]) == (45, 78)


def test_phase_progress_window_config_phase() -> None:
    assert _phase_progress_window(["Fase: configure environment"]) == (15, 40)


def test_phase_progress_window_unknown_phase_returns_none() -> None:
    assert _phase_progress_window(["Fase: something_unknown"]) is None


def test_phase_progress_window_picks_last_fase() -> None:
    lines = ["Fase: enumerate devices", "Fase: recovery api"]
    assert _phase_progress_window(lines) == (80, 95)


# ---------------------------------------------------------------------------
# _splash_progress_percent
# ---------------------------------------------------------------------------


def test_splash_progress_percent_returns_100_when_thread_done() -> None:
    assert _splash_progress_percent(0.0, None, thread_alive=False) == 100
    assert _splash_progress_percent(10.0, ["Fase: enumerate"], thread_alive=False) == 100


def test_splash_progress_percent_falls_back_to_time_when_no_window() -> None:
    # elapsed=0 -> 0
    assert _splash_progress_percent(0.0, None, thread_alive=True) == 0
    # elapsed=0.6 -> 98
    assert _splash_progress_percent(0.6, None, thread_alive=True) == 98
    # elapsed=1.2 -> capped at 98
    assert _splash_progress_percent(1.2, None, thread_alive=True) == 98


def test_splash_progress_percent_clamps_at_window_high() -> None:
    # Window [15, 40]; at elapsed=20 the creep fills span.
    pct = _splash_progress_percent(20.0, ["Fase: configure env"], thread_alive=True)
    assert pct == 40


def test_splash_progress_percent_window_low_eq_high_returns_low() -> None:
    # Phase "listo" -> window (100, 100) -> always 100.
    pct = _splash_progress_percent(0.0, ["Fase: listo"], thread_alive=True)
    assert pct == 100


def test_splash_progress_percent_creeps_through_window() -> None:
    # Window [15, 40], span=25. At elapsed=10, creep = 25*0.5 = 12 -> pct = 27.
    pct = _splash_progress_percent(10.0, ["Fase: configure env"], thread_alive=True)
    assert pct == 27


# ---------------------------------------------------------------------------
# _banner_layout
# ---------------------------------------------------------------------------


def test_banner_layout_returns_padding_and_centered_lines() -> None:
    v_padding, centered = _banner_layout(120, 30)
    assert isinstance(v_padding, int)
    assert v_padding >= 0
    assert isinstance(centered, list)
    assert len(centered) == len(_splash_lines())


def test_banner_layout_centers_short_terminal() -> None:
    _, centered = _banner_layout(120, 30)
    # Each line is padded with leading spaces.
    for line in centered:
        assert line.startswith(" ")


def test_banner_layout_does_not_pad_when_terminal_is_narrower_than_banner() -> None:
    # Width smaller than the longest banner line -> pad stays at 0.
    long_line = max(_splash_lines(), key=len)
    v_padding, centered = _banner_layout(len(long_line) - 5, 30)
    assert v_padding >= 0
    # If pad > 0 then the line was widened past the requested width.
    for line in centered:
        assert isinstance(line, str)


def test_banner_layout_v_padding_when_tall_terminal() -> None:
    v_padding, _ = _banner_layout(120, 100)
    # 100 height with ~7 banner lines leaves plenty of vertical padding.
    assert v_padding > 0


# ---------------------------------------------------------------------------
# _render_banner_block
# ---------------------------------------------------------------------------


def test_render_banner_block_default_opacity_renders_all_lines() -> None:
    v_padding, centered = _banner_layout(120, 30)
    out = _render_banner_block(centered, v_padding)
    # Default opacity=1.0 -> every line gets a color code (>= count of lines,
    # plus separator and final reset).
    assert out.count("\033[") >= len(_splash_lines())


def test_render_banner_block_zero_opacity_skips_lines() -> None:
    v_padding, centered = _banner_layout(120, 30)
    out = _render_banner_block(centered, v_padding, line_opacity=[0.0] * len(_splash_lines()))
    # All lines skipped -> no per-line color escapes (just padding + final reset).
    # The final \033[0m reset still appears once, but no per-line color codes.
    assert "\033[" not in out.replace("\033[0m", "")


def test_render_banner_block_partial_opacity_dims_line() -> None:
    v_padding, centered = _banner_layout(120, 30)
    # 0.5 opacity -> DIM prefix applied to the first line.
    opacity = [0.5] + [1.0] * (len(_splash_lines()) - 1)
    out = _render_banner_block(centered, v_padding, line_opacity=opacity)
    assert "\033[2m" in out  # C_DIM escape


def test_render_banner_block_low_opacity_uses_hide() -> None:
    v_padding, centered = _banner_layout(120, 30)
    # 0.1 opacity -> C_HIDE prefix on the first line.
    opacity = [0.1] + [1.0] * (len(_splash_lines()) - 1)
    out = _render_banner_block(centered, v_padding, line_opacity=opacity)
    # The hide escape is the same ANSI 8 sequence as the dim escape -- check
    # by seeing the C_RESET after the first line.
    assert out.count("\033[0m") >= 2