"""Tests forensics SDRplay (sin hardware)."""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from core.sdrplay_forensics import (
    _CRASH_KEYWORDS,
    _filter_entries_since,
    _iter_dump_files,
    _wer_report_archive_root,
    collect_event_log_after_crash,
    find_latest_wer_report_fallback,
    find_recent_minidump,
    find_wer_report_artifacts,
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


# ---------------------------------------------------------------------------
# Helpers puros
# ---------------------------------------------------------------------------


def test_crash_keywords_matches_python():
    assert _CRASH_KEYWORDS.search("python crashed")
    assert _CRASH_KEYWORDS.search("sdrplay fault")
    assert _CRASH_KEYWORDS.search("SoapySDR error")
    assert _CRASH_KEYWORDS.search("sdrPlaySupport")


def test_crash_keywords_skips_unrelated():
    assert not _CRASH_KEYWORDS.search("audio buffer underrun")
    assert not _CRASH_KEYWORDS.search("")


def test_filter_entries_since_keeps_iso_timestamp_within_window():
    ts = datetime.now(timezone.utc).replace(microsecond=0)
    line = ts.isoformat() + " [Application] Id=1000 python fault"
    assert _filter_entries_since([line], since=ts.timestamp() - 1) == [line]


def test_filter_entries_since_skips_old_timestamp():
    old = "2020-01-01T00:00:00 [Application] Id=1000 python fault"
    recent = datetime.now(timezone.utc).timestamp()
    assert _filter_entries_since([old], since=recent) == []


def test_filter_entries_since_accepts_within_15s_tolerance():
    """El filtro tolera timestamps hasta 15s antes de `since`."""
    past = datetime.now(timezone.utc).replace(microsecond=0)
    line = past.isoformat() + " [Application] Id=1000 sdrplay"
    # since 5s después: ts = since - 5, dentro de tolerancia 15s.
    since = past.timestamp() + 5
    assert _filter_entries_since([line], since=since) == [line]


def test_filter_entries_since_skips_outside_15s_tolerance():
    past = datetime.now(timezone.utc).replace(microsecond=0)
    line = past.isoformat() + " [Application] Id=1000 sdrplay"
    # since 30s después: ts = since - 30, fuera de tolerancia 15s.
    since = past.timestamp() + 30
    assert _filter_entries_since([line], since=since) == []


def test_filter_entries_since_falls_back_to_date_header():
    """Si no hay ISO al inicio, intenta extraer 'Date:' del cuerpo."""
    ts = datetime.now(timezone.utc).replace(microsecond=0)
    line = f"Some header\nDate: {ts.isoformat()}\nMore lines"
    assert _filter_entries_since([line], since=ts.timestamp() - 1) == [line]


def test_filter_entries_since_strips_microseconds_in_date_fallback():
    ts = datetime.now(timezone.utc).replace(microsecond=123456)
    line = f"Date: {ts.isoformat()}\nMore"
    assert _filter_entries_since([line], since=ts.timestamp() - 1) == [line]


def test_filter_entries_since_drops_unparseable():
    """Líneas sin timestamp reconocible se descartan."""
    assert _filter_entries_since(["random text without date"], since=time.time()) == []


def test_filter_entries_since_handles_short_lines():
    assert _filter_entries_since(["2024-01-01", "abc"], since=0) == []


def test_filter_entries_since_drops_invalid_iso():
    """Si el ISO al inicio tiene mal formato, cae al fallback o se descarta."""
    line = "2024-13-99T99:99:99 garbage"
    # No match al inicio; sin Date: header — descartado.
    assert _filter_entries_since([line], since=time.time()) == []


def test_iter_dump_files_empty_when_missing(tmp_path):
    assert _iter_dump_files(tmp_path / "missing") == []


def test_iter_dump_files_finds_python_dmp(tmp_path):
    dmp = tmp_path / "python.exe.123.dmp"
    dmp.write_bytes(b"")
    found = _iter_dump_files(tmp_path)
    assert dmp in found


def test_iter_dump_files_finds_sdrplay_dmp(tmp_path):
    dmp = tmp_path / "sdrplay.dmp"
    dmp.write_bytes(b"")
    found = _iter_dump_files(tmp_path)
    assert dmp in found


def test_iter_dump_files_finds_soapysdr_dmp(tmp_path):
    dmp = tmp_path / "SoapySDR.dll.dmp"
    dmp.write_bytes(b"")
    found = _iter_dump_files(tmp_path)
    assert dmp in found


def test_iter_dump_files_finds_recursive(tmp_path):
    sub = tmp_path / "sub" / "deep"
    sub.mkdir(parents=True)
    dmp = sub / "python.exe.456.dmp"
    dmp.write_bytes(b"")
    found = _iter_dump_files(tmp_path)
    assert dmp in found


def test_iter_dump_files_ignores_other_extensions(tmp_path):
    (tmp_path / "python.exe.log").write_bytes(b"")
    (tmp_path / "readme.txt").write_bytes(b"")
    found = _iter_dump_files(tmp_path)
    assert found == []


def test_wer_report_archive_root_uses_programdata(monkeypatch):
    monkeypatch.setenv("ProgramData", r"C:\ProgramData")
    root = _wer_report_archive_root()
    assert str(root).endswith(os.path.join("Microsoft", "Windows", "WER", "ReportArchive"))


def test_wer_report_archive_root_default_when_unset(monkeypatch):
    monkeypatch.delenv("ProgramData", raising=False)
    root = _wer_report_archive_root()
    assert "ProgramData" in str(root)


def test_find_wer_report_artifacts_empty_when_root_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("core.sdrplay_forensics._wer_report_archive_root", lambda: tmp_path / "missing")
    assert find_wer_report_artifacts(since=0) == []


def test_find_wer_report_artifacts_copies_recent(tmp_path, monkeypatch):
    archive = tmp_path / "ReportArchive"
    archive.mkdir()
    folder = archive / "AppCrash_python.exe_123_abc"
    folder.mkdir()
    (folder / "Report.wer").write_text("crash info")
    (folder / "python.exe.123.dmp").write_bytes(b"MDMP")
    monkeypatch.setattr("core.sdrplay_forensics._wer_report_archive_root", lambda: archive)
    # dumps_dir via env
    monkeypatch.setenv("XYZ_SDR_WER_DUMP_FOLDER", str(tmp_path))
    staged = find_wer_report_artifacts(since=time.time() - 3600)
    assert len(staged) == 2
    for path in staged:
        assert Path(path).is_file()


def test_find_wer_report_artifacts_skips_old(tmp_path, monkeypatch):
    archive = tmp_path / "ReportArchive"
    archive.mkdir()
    folder = archive / "AppCrash_python.exe_999"
    folder.mkdir()
    (folder / "Report.wer").write_text("old crash")
    monkeypatch.setattr("core.sdrplay_forensics._wer_report_archive_root", lambda: archive)
    monkeypatch.setenv("XYZ_SDR_WER_DUMP_FOLDER", str(tmp_path))
    # since en el futuro: todo está "viejo"
    staged = find_wer_report_artifacts(since=time.time() + 3600)
    assert staged == []


def test_find_wer_report_artifacts_skips_non_matching_names(tmp_path, monkeypatch):
    archive = tmp_path / "ReportArchive"
    archive.mkdir()
    folder = archive / "AppCrash_chrome.exe_999"
    folder.mkdir()
    (folder / "Report.wer").write_text("chrome crash")
    monkeypatch.setattr("core.sdrplay_forensics._wer_report_archive_root", lambda: archive)
    monkeypatch.setenv("XYZ_SDR_WER_DUMP_FOLDER", str(tmp_path))
    staged = find_wer_report_artifacts(since=time.time() - 3600)
    assert staged == []


def test_find_latest_wer_report_fallback_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("core.sdrplay_forensics._wer_report_archive_root", lambda: tmp_path / "missing")
    assert find_latest_wer_report_fallback() == []


def test_find_latest_wer_report_fallback_copies_reports(tmp_path, monkeypatch):
    archive = tmp_path / "ReportArchive"
    archive.mkdir()
    for i in range(3):
        folder = archive / f"AppCrash_python.exe_{i:04d}"
        folder.mkdir()
        (folder / "Report.wer").write_text(f"crash {i}")
    monkeypatch.setattr("core.sdrplay_forensics._wer_report_archive_root", lambda: archive)
    monkeypatch.setenv("XYZ_SDR_WER_DUMP_FOLDER", str(tmp_path))
    staged = find_latest_wer_report_fallback(limit=2)
    assert len(staged) == 2


def test_find_latest_wer_report_fallback_skips_folder_without_report(tmp_path, monkeypatch):
    archive = tmp_path / "ReportArchive"
    archive.mkdir()
    folder = archive / "AppCrash_python.exe_0001"
    folder.mkdir()
    # sin Report.wer
    monkeypatch.setattr("core.sdrplay_forensics._wer_report_archive_root", lambda: archive)
    monkeypatch.setenv("XYZ_SDR_WER_DUMP_FOLDER", str(tmp_path))
    assert find_latest_wer_report_fallback() == []


def test_stage_minidump_for_report_missing_source(tmp_path):
    """Si el source no existe, devuelve '' (vacío)."""
    assert stage_minidump_for_report(str(tmp_path / "missing.dmp"), dest_dir=tmp_path / "out") == ""


def test_stage_minidump_for_report_creates_dest_dir(tmp_path):
    src = tmp_path / "python.exe.1.dmp"
    src.write_bytes(b"MDMP")
    nested_dest = tmp_path / "deep" / "nested" / "out"
    staged = stage_minidump_for_report(str(src), dest_dir=nested_dest, tag="segfault")
    assert Path(staged).is_file()
    assert nested_dest.is_dir()
    assert "segfault" in staged


def test_stage_minidump_for_report_uses_custom_tag(tmp_path):
    src = tmp_path / "python.exe.1.dmp"
    src.write_bytes(b"MDMP")
    staged = stage_minidump_for_report(str(src), dest_dir=tmp_path, tag="my-tag")
    assert "my-tag" in Path(staged).name


def test_stage_minidump_for_report_returns_source_on_copy_error(tmp_path, monkeypatch):
    src = tmp_path / "python.exe.1.dmp"
    src.write_bytes(b"MDMP")
    # Forzar OSError al copiar.
    import shutil as sh

    monkeypatch.setattr(sh, "copy2", lambda *_a, **_kw: (_ for _ in ()).throw(OSError("boom")))
    staged = stage_minidump_for_report(str(src), dest_dir=tmp_path)
    assert staged == str(src)


def test_minidump_search_roots_dedupes(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    dumps = tmp_path / "dumps"
    dumps.mkdir()
    # dumps_dir coincide con local/CrashDumps/xyz-sdr/dumps -> dedup.
    roots = minidump_search_roots(dumps_dir=dumps)
    keys = [str(r).lower() for r in roots]
    assert len(keys) == len(set(keys))
