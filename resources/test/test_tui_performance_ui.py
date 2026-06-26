"""Tests del preset de rendimiento TUI (FPS, cascada, sidebar)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tui.app import PERFORMANCE_DISPLAY_FPS, PERFORMANCE_WATERFALL_FPS, XyzSDRApp


def test_performance_ui_caps_display_fps():
    app = XyzSDRApp(config={"app": {"performance_ui": True}, "dsp": {"display_fps": 20}, "display": {}})
    assert app._display_fps_cap() == PERFORMANCE_DISPLAY_FPS


def test_performance_ui_respects_lower_display_fps():
    app = XyzSDRApp(config={"app": {"performance_ui": True}, "dsp": {"display_fps": 8}, "display": {}})
    assert app._display_fps_cap() == 8.0


def test_performance_ui_waterfall_default_speed():
    app = XyzSDRApp(config={"app": {"performance_ui": True}, "dsp": {}, "display": {}})
    assert app._initial_waterfall_speed() == PERFORMANCE_WATERFALL_FPS


def test_waterfall_scroll_fps_from_config():
    app = XyzSDRApp(
        config={
            "app": {"performance_ui": True},
            "dsp": {},
            "display": {"waterfall_scroll_fps": 5},
        }
    )
    assert app._initial_waterfall_speed() == 5


def test_toggle_sidebar_collapses_controls():
    app = XyzSDRApp()
    panel = MagicMock()

    with patch.object(app, "query_one", return_value=panel), patch.object(
        app, "call_after_refresh"
    ), patch.object(app, "_log"):
        app.action_toggle_sidebar()
        assert app._sidebar_collapsed is True
        panel.add_class.assert_called_once_with("-collapsed")

        app.action_toggle_sidebar()
        assert app._sidebar_collapsed is False
        panel.remove_class.assert_called_once_with("-collapsed")
