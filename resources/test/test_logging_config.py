"""Tests for core/logging_config.py -- Textual-safe root logger setup."""

from __future__ import annotations

import logging

import pytest

from core.logging_config import (
    _SESSION_LOGGER,
    detach_console_logging,
    preserve_session_file_handler,
)


@pytest.fixture(autouse=True)
def _isolate_root_logger():
    """Snapshot root handlers + raiseExceptions + session logger propagate; restore after each test."""
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_raise = logging.raiseExceptions
    session = logging.getLogger(_SESSION_LOGGER)
    saved_propagate = session.propagate
    saved_session_handlers = list(session.handlers)
    try:
        yield
    finally:
        root.handlers = saved_handlers
        logging.raiseExceptions = saved_raise
        session.propagate = saved_propagate
        session.handlers = saved_session_handlers


def test_detach_console_logging_removes_stream_handlers() -> None:
    root = logging.getLogger()
    stream = logging.StreamHandler()
    root.addHandler(stream)
    root.addHandler(logging.NullHandler())

    detach_console_logging()

    # StreamHandler without a Stream is a fake; here we attach a plain
    # StreamHandler which is not a FileHandler, so it must be removed.
    handler_types = [type(h) for h in root.handlers]
    assert logging.StreamHandler not in handler_types


def test_detach_console_logging_keeps_file_handlers() -> None:
    root = logging.getLogger()
    fh = logging.FileHandler("ignored.log")
    root.addHandler(fh)
    try:
        detach_console_logging()
        assert fh in root.handlers
    finally:
        try:
            fh.close()
        except Exception:
            pass
        root.removeHandler(fh)


def test_detach_console_logging_adds_null_handler_when_empty() -> None:
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    detach_console_logging()

    assert any(isinstance(h, logging.NullHandler) for h in root.handlers)
    # Also disables propagation noise that breaks Textual on broken stdio.
    assert logging.raiseExceptions is False


def test_preserve_session_file_handler_noop_when_no_session_logger() -> None:
    # Session logger has no handlers -> propagate stays True
    session = logging.getLogger(_SESSION_LOGGER)
    session.propagate = True
    for h in list(session.handlers):
        session.removeHandler(h)
    assert not session.handlers

    preserve_session_file_handler()
    assert session.propagate is True


def test_preserve_session_file_handler_disables_propagate_with_handlers() -> None:
    session = logging.getLogger(_SESSION_LOGGER)
    fake = logging.NullHandler()
    session.addHandler(fake)
    try:
        preserve_session_file_handler()
        assert session.propagate is False
    finally:
        session.removeHandler(fake)