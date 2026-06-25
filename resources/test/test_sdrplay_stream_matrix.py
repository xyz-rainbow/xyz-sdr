"""Tests del harness de matriz SDRplay (sin hardware)."""
from __future__ import annotations

from core.sdrplay_stream_matrix import MatrixRow, build_matrix_cases, format_matrix_summary, MatrixReport


def test_build_matrix_cases_count():
    cases = build_matrix_cases(profiles=("default",))
    assert len(cases) == 16  # 2 modes x 2 formats x 4 rates


def test_build_matrix_cases_both_profiles():
    cases = build_matrix_cases(profiles=("default", "bundled-only"))
    assert len(cases) == 32
    assert {c.runtime_profile for c in cases} == {"default", "bundled-only"}


def test_format_matrix_summary_no_best():
    report = MatrixReport(
        generated_at="2026-01-01T00:00:00Z",
        hostname="test",
        rows=[MatrixRow(sample_rate=500_000, format="CF32", stream_mode="minimal", result="SEGFAULT")],
    )
    text = format_matrix_summary(report)
    assert "matrix_version: 0.3" in text
    assert "best: (none OK)" in text
    assert "SEGFAULT=1" in text


def test_matrix_dry_run_cs16_not_skip(monkeypatch):
    from core.sdrplay_stream_matrix import run_matrix

    monkeypatch.setenv("XYZ_SDR_MATRIX_PROFILES", "default")
    report = run_matrix(dry_run=True)
    cs16 = [r for r in report.rows if r.format == "CS16"]
    assert len(cs16) == 8
    assert all(r.result == "PENDING" for r in cs16)
