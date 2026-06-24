"""Tests de core/bookmarks: carga, export/import y fusión."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.bookmarks import (
    export_bookmarks,
    import_bookmarks,
    load_bookmarks,
    merge_bookmarks,
    parse_bookmarks_data,
    save_bookmarks,
)

FALLBACK = [("FM Test", 100_000_000.0, "wbfm")]


def test_parse_bookmarks_data_skips_invalid_entries():
    data = {
        "bookmarks": [
            {"name": "A", "freq_hz": 88_000_000, "mode": "wbfm"},
            "bad",
            {"name": "B", "freq_hz": 108_000_000, "mode": "nbfm"},
        ]
    }
    assert parse_bookmarks_data(data) == [
        ("A", 88_000_000.0, "wbfm"),
        ("B", 108_000_000.0, "nbfm"),
    ]


def test_load_bookmarks_creates_file_with_fallback(tmp_path: Path):
    path = tmp_path / "bookmarks.toml"
    loaded = load_bookmarks(path, FALLBACK)
    assert loaded == FALLBACK
    assert path.is_file()


def test_save_and_import_roundtrip(tmp_path: Path):
    path = tmp_path / "bookmarks.toml"
    bookmarks = [
        ("Radio 1", 96_300_000.0, "wbfm"),
        ("ATC", 118_500_000.0, "nbfm"),
    ]
    save_bookmarks(path, bookmarks)
    assert import_bookmarks(path, FALLBACK) == bookmarks


def test_export_bookmarks_writes_dest(tmp_path: Path):
    dest = tmp_path / "export.toml"
    bookmarks = [("X", 50_000_000.0, "am")]
    export_bookmarks(bookmarks, dest)
    assert import_bookmarks(dest, FALLBACK) == bookmarks


def test_import_bookmarks_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        import_bookmarks(tmp_path / "missing.toml", FALLBACK)


def test_merge_bookmarks_deduplicates_by_freq_and_mode():
    base = [("A", 100_000_000.0, "wbfm")]
    imported = [
        ("A dup", 100_000_000.5, "wbfm"),
        ("B", 101_000_000.0, "wbfm"),
        ("A other mode", 100_000_000.0, "am"),
    ]
    merged = merge_bookmarks(base, imported)
    assert len(merged) == 3
    assert merged[0] == base[0]
    assert merged[1][0] == "B"
    assert merged[2][2] == "am"
