"""Tests forensics SDRplay (sin hardware)."""
from __future__ import annotations

import time
from pathlib import Path

from core.sdrplay_forensics import (
    collect_event_log_after_crash,
    find_recent_minidump,
    minidump_search_roots,
    stage_minidump_for_report,
)


def test_minidump_search_roots_includes_crashdumps(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    crash = tmp_path / "CrashDumps"
    crash.mkdir()
    roots = minidump_search_roots(dumps_dir=tmp_path / "dumps")
    assert crash in roots


def test_find_recent_minidump_picks_python_dmp(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    crash = tmp_path / "CrashDumps"
    crash.mkdir()
    dmp = crash / "python.exe.1234.dmp"
    dmp.write_bytes(b"MDMP")
    since = time.time() - 60
    found = find_recent_minidump(since=since, dumps_dir=tmp_path / "dumps", poll_seconds=0)
    assert found.endswith("python.exe.1234.dmp")


def test_stage_minidump_for_report(tmp_path):
    src = tmp_path / "python.exe.1.dmp"
    src.write_bytes(b"MDMP")
    staged = stage_minidump_for_report(str(src), dest_dir=tmp_path / "out", tag="test")
    assert staged
    assert Path(staged).is_file()


def test_collect_event_log_non_windows(monkeypatch):
    monkeypatch.setattr("core.sdrplay_forensics.os.name", "posix")
    entries, note = collect_event_log_after_crash(minutes=1)
    assert entries == []
    assert "not Windows" in note
