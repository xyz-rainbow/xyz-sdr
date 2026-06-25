"""Tests del harness de matriz SDRplay (sin hardware)."""
from __future__ import annotations

from core.sdrplay_stream_matrix import MatrixRow, build_matrix_cases, format_matrix_summary, MatrixReport


def test_build_matrix_cases_count():
    cases = build_matrix_cases()
    assert len(cases) == 16  # 2 modes x 2 formats x 4 rates


def test_format_matrix_summary_no_best():
    report = MatrixReport(
        generated_at="2026-01-01T00:00:00Z",
        hostname="test",
        rows=[MatrixRow(sample_rate=500_000, format="CF32", stream_mode="minimal", result="SEGFAULT")],
    )
    text = format_matrix_summary(report)
    assert "best: (none OK)" in text
    assert "SEGFAULT=1" in text
