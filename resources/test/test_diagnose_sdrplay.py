"""Tests de diagnóstico SDRplay (smoke / mocks)."""

from __future__ import annotations

from core.diagnose_sdrplay import (
    DiagnoseReport,
    _analyze_report,
    _probe_output_ok,
    format_diagnose_report,
)


def test_analyze_report_flags_legacy_plugin():
    report = DiagnoseReport(plugin_status="legacy")
    _analyze_report(report)
    assert any("LEGACY" in issue for issue in report.issues)
    assert report.recommendations


def test_analyze_report_stream_fail():
    report = DiagnoseReport(find_ok=True, stream_test_ok=False)
    _analyze_report(report)
    assert any("stream test" in issue.lower() for issue in report.issues)


def test_analyze_report_stream_segfault():
    report = DiagnoseReport(
        stream_test_segfault=True,
        find_ok=True,
        plugin_status="present",
    )
    _analyze_report(report)
    assert any("crash nativo" in issue.lower() for issue in report.issues)
    assert any("install_sdrplay_api.bat" in rec for rec in report.recommendations)
    assert any("install_soapy_sdrplay3" in rec for rec in report.recommendations)


def test_format_diagnose_report_probe_skipped():
    report = DiagnoseReport(probe_skipped=True)
    text = format_diagnose_report(report)
    assert "SoapySDRUtil --probe sdrplay: SKIPPED" in text


def test_analyze_report_adds_volk_note_when_only_volk_warning():
    report = DiagnoseReport(
        find_stdout="[WARNING] SoapyVOLKConverters: no VOLK config file found.",
    )
    _analyze_report(report)
    assert any("volk" in rec.lower() for rec in report.recommendations)


def test_is_native_crash_windows_codes():
    from core.sdrplay_service import is_native_crash_exit_code

    assert is_native_crash_exit_code(3221225477)
    assert is_native_crash_exit_code(-1073741819)
    assert not is_native_crash_exit_code(0)


def test_probe_output_ok_detects_rsp():
    text = "driver=SDRplay\nhardware=RSP1\n"
    assert _probe_output_ok(text)


def test_probe_output_ok_rejects_api_open_fail():
    text = (
        "Probe device driver=sdrplay\n"
        "[ERROR] sdrplay_api_Open() Error: sdrplay_api_Fail\n"
        "Error probing device: no available RSP devices found\n"
    )
    assert not _probe_output_ok(text)


def test_analyze_report_service_stopped_api_open():
    report = DiagnoseReport(
        service_running=False,
        find_stdout="[ERROR] sdrplay_api_Open() Error: sdrplay_api_Fail",
    )
    _analyze_report(report)
    assert any("detenido" in issue.lower() for issue in report.issues)


def test_format_diagnose_report_includes_sections():
    report = DiagnoseReport(
        timestamp="2026-01-01T00:00:00",
        plugin_status="present",
        issues=["example issue"],
        recommendations=["example rec"],
    )
    text = format_diagnose_report(report)
    assert "=== xyz-sdr SDRplay diagnose ===" in text
    assert "ISSUES" in text
    assert "example issue" in text


def test_analyze_report_probe_degraded():
    report = DiagnoseReport(
        probe_segfault=True,
        probe_ok_degraded=True,
        probe_stdout="driver=SDRplay\nhardware=RSP1\n",
    )
    _analyze_report(report)
    assert any("identificó el RSP1" in issue for issue in report.issues)
    assert not any("antes de identificar" in issue for issue in report.issues)


def test_analyze_report_stream_timeout():
    report = DiagnoseReport(
        find_ok=True,
        stream_test_ok=False,
        stream_test_last_step="timeout",
    )
    _analyze_report(report)
    assert any("timeout" in issue.lower() for issue in report.issues)
    assert any("XYZ_SDR_PREFLIGHT_TIMEOUT" in rec for rec in report.recommendations)


def test_analyze_report_probe_segfault_without_identification():
    report = DiagnoseReport(
        probe_segfault=True,
        probe_ok_degraded=False,
        probe_stdout="Probe device driver=sdrplay\nError probing device\n",
    )
    _analyze_report(report)
    assert any("antes de identificar" in issue for issue in report.issues)


def test_format_diagnose_report_probe_degraded():
    report = DiagnoseReport(
        probe_ok_degraded=True,
        probe_segfault=True,
        probe_stdout="hardware=RSP1\n",
    )
    text = format_diagnose_report(report)
    assert "SoapySDRUtil --probe sdrplay: DEGRADED" in text


def test_analyze_report_stream_service_not_responding():
    report = DiagnoseReport(
        find_ok=True,
        stream_test_ok=False,
        stream_test_last_step="bootstrap",
        stream_test_detail="ERR no available RSP devices\nServiceNotResponding",
    )
    _analyze_report(report)
    assert any("ServiceNotResponding" in issue for issue in report.issues)


def test_collect_diagnose_restarts_service_after_probe(monkeypatch):
    from core.diagnose_sdrplay import collect_diagnose_report

    restarts: list[str] = []

    monkeypatch.setattr(
        "core.diagnose_sdrplay.bootstrap_soapy",
        lambda **_: type("S", (), {"import_ok": True, "devices": []})(),
    )
    monkeypatch.setattr(
        "core.diagnose_sdrplay._run_soapy_util",
        lambda args, timeout=15.0: type(
            "R",
            (),
            {
                "stdout": "hardware=RSP1\n" if "probe" in args[0] else "Found device 0\n",
                "stderr": "",
                "returncode": -1073741819 if "probe" in args[0] else 0,
            },
        )(),
    )
    monkeypatch.setattr(
        "core.diagnose_sdrplay._run_stream_path_tests",
        lambda stream_timeout=None: (
            type("P", (), {"ok": True, "segfault": False, "last_step": "done", "detail": "OK"})(),
            type("P", (), {"ok": False, "segfault": False, "last_step": "timeout", "detail": ""})(),
        ),
    )
    monkeypatch.setattr(
        "core.diagnose_sdrplay._restart_service_before_stream_test",
        lambda: restarts.append("ok") or (True, "restarted"),
    )
    monkeypatch.setattr("core.diagnose_sdrplay.find_pothos_install", lambda: "C:\\Pothos")
    monkeypatch.setattr("core.diagnose_sdrplay.find_sdrplay_api_dll", lambda: "api.dll")
    monkeypatch.setattr("core.diagnose_sdrplay.find_sdrplay_soapy_module", lambda _p: "mod.dll")
    monkeypatch.setattr("core.diagnose_sdrplay.assess_sdrplay_soapy_module", lambda _p: "present")
    monkeypatch.setattr("core.diagnose_sdrplay.soapy_plugin_search_dirs", lambda _p: [])
    monkeypatch.setattr("core.diagnose_sdrplay.user_soapy_plugin_dir", lambda: "user")
    monkeypatch.setattr("core.diagnose_sdrplay.user_xyz_sdr_bin_dir", lambda: "bin")
    monkeypatch.setattr("core.diagnose_sdrplay.check_sdrplay_service_running", lambda: True)

    report = collect_diagnose_report(run_stream_test=True, run_probe=True)
    assert restarts == ["ok"]
    assert report.probe_ok_degraded
    assert report.stream_test_minimal_ok


def test_format_diagnose_report_includes_stream_paths():
    report = DiagnoseReport(
        stream_test_ok=True,
        stream_test_legacy_ok=False,
        stream_test_minimal_ok=True,
        stream_test_recommended_path="minimal",
    )
    text = format_diagnose_report(report)
    assert "stream test minimal: OK" in text
    assert "stream test recommended path: minimal" in text
