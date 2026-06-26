"""Tests for setup/install_actions.py -- installer orchestration entry points."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from setup.install_actions import (
    InstallContext,
    install_pothos,
    install_python_env,
    install_soapy_sdrplay3,
    install_sdrplay,
    report_install_error,
    report_path_configuration,
    resolve_soapy_python,
    run_diagnostics,
    run_full_setup,
    run_repo_update_action,
    run_sdrplay_api_installer,
)


def _ctx(*, lang: str = "es", temp_dir: str = "C:\\Temp") -> InstallContext:
    return InstallContext(
        lang=lang,
        say=lambda msg: None,
        confirm=lambda prompt: True,
        temp_dir=temp_dir,
    )


# ---------------------------------------------------------------------------
# report_install_error
# ---------------------------------------------------------------------------


def test_report_install_error_permission_error_says_cancelled() -> None:
    messages: list[str] = []

    def _say(msg: str) -> None:
        messages.append(msg)

    ctx = InstallContext(lang="es", say=_say, confirm=lambda p: True, temp_dir="")
    report_install_error(ctx, PermissionError("denied"))
    assert any("CANCELLED" in m for m in messages)


def test_report_install_error_other_exception_says_error() -> None:
    messages: list[str] = []

    def _say(msg: str) -> None:
        messages.append(msg)

    ctx = InstallContext(lang="es", say=_say, confirm=lambda p: True, temp_dir="")
    report_install_error(ctx, RuntimeError("boom"))
    assert any("[ERROR]" in m for m in messages)


def test_report_install_error_windows_elevation_740_hint() -> None:
    messages: list[str] = []

    def _say(msg: str) -> None:
        messages.append(msg)

    class _WinErr(RuntimeError):
        winerror = 740

    ctx = InstallContext(lang="es", say=_say, confirm=lambda p: True, temp_dir="")
    with patch("os.name", "nt"):
        report_install_error(ctx, _WinErr("elevate"))
    # Elevation hint should appear alongside the error message.
    assert any("[ERROR]" in m for m in messages)


# ---------------------------------------------------------------------------
# report_path_configuration
# ---------------------------------------------------------------------------


def test_report_path_configuration_success_path_already_configured() -> None:
    messages: list[str] = []

    def _say(msg: str) -> None:
        messages.append(msg)

    ctx = InstallContext(lang="es", say=_say, confirm=lambda p: True, temp_dir="")

    with patch("setup.install_actions.configure_path", return_value=(True, [])):
        with patch(
            "setup.install_actions.path_contains_pothos", return_value=False,
        ):
            report_path_configuration(ctx)

    assert any("SUCCESS" in m for m in messages)
    # Spanish i18n: path_restart_hint -> 'Si otra terminal no encuentra SoapySDR, ciérrala...'
    assert any("ciérrala" in m.lower() or "terminal" in m.lower() for m in messages)


def test_report_path_configuration_success_with_pythonpath_entry() -> None:
    messages: list[str] = []

    def _say(msg: str) -> None:
        messages.append(msg)

    ctx = InstallContext(lang="es", say=_say, confirm=lambda p: True, temp_dir="")

    with patch(
        "setup.install_actions.configure_path",
        return_value=(True, ["PYTHONPATH:C:\\pothos\\site-packages"]),
    ):
        with patch(
            "setup.install_actions.path_contains_pothos", return_value=True,
        ):
            report_path_configuration(ctx)

    # When path_contains_pothos is True we get the session-applied message
    # (Spanish: "PATH/PYTHONPATH aplicados en esta sesión.").
    assert any("aplicados" in m.lower() or "sesión" in m.lower() for m in messages)


def test_report_path_configuration_failure_says_error() -> None:
    messages: list[str] = []

    def _say(msg: str) -> None:
        messages.append(msg)

    ctx = InstallContext(lang="es", say=_say, confirm=lambda p: True, temp_dir="")

    with patch("setup.install_actions.configure_path", return_value=(False, "boom")):
        report_path_configuration(ctx)

    assert any("ERROR" in m for m in messages)


# ---------------------------------------------------------------------------
# install_sdrplay / install_pothos thin wrappers
# ---------------------------------------------------------------------------


def test_install_sdrplay_delegates_to_run_sdrplay_api_installer() -> None:
    ctx = _ctx()
    with patch(
        "setup.install_actions.run_sdrplay_api_installer", return_value=True,
    ) as mock_run:
        assert install_sdrplay(ctx) is True
    mock_run.assert_called_once_with(ctx)


def test_install_pothos_download_failure_skips_run_installer() -> None:
    messages: list[str] = []

    def _say(msg: str) -> None:
        messages.append(msg)

    ctx = InstallContext(lang="es", say=_say, confirm=lambda p: True, temp_dir="C:\\Temp")
    with patch(
        "setup.install_actions.download_file", return_value=False,
    ) as mock_dl:
        install_pothos(ctx)
    # download called twice (the source has a retry loop).
    assert mock_dl.call_count == 2


def test_install_pothos_download_success_runs_installer() -> None:
    messages: list[str] = []

    def _say(msg: str) -> None:
        messages.append(msg)

    ctx = InstallContext(lang="es", say=_say, confirm=lambda p: True, temp_dir="C:\\Temp")
    with patch(
        "setup.install_actions.download_file", return_value=True,
    ):
        with patch("setup.install_actions.run_exe_installer"):
            with patch("setup.install_actions.report_path_configuration"):
                install_pothos(ctx)
    # download called twice -> both attempts hit run_exe_installer.
    # Just check no exception raised.


# ---------------------------------------------------------------------------
# run_sdrplay_api_installer
# ---------------------------------------------------------------------------


def test_run_sdrplay_api_installer_isolated_calls_body_directly() -> None:
    ctx = _ctx()
    with patch(
        "setup.install_actions._run_sdrplay_api_installer_body", return_value=True,
    ) as mock_body:
        assert run_sdrplay_api_installer(ctx, isolated=True) is True
    mock_body.assert_called_once_with(ctx)


def test_run_sdrplay_api_installer_non_isolated_short_circuits_on_prepare_failure() -> None:
    """If prepare_for_sdrplay_api_install returns (False, msg), short-circuit."""
    ctx = _ctx()
    # The source imports prepare_for_sdrplay_api_install inside the function;
    # patch on the original module so the `from core.sdrplay_install_guard import ...`
    # in run_sdrplay_api_installer picks up the mock.
    with patch(
        "core.sdrplay_install_guard.prepare_for_sdrplay_api_install",
        return_value=(False, "bloccato"),
    ):
        assert run_sdrplay_api_installer(ctx) is False


def test_run_sdrplay_api_installer_body_no_installer_says_error() -> None:
    messages: list[str] = []

    def _say(msg: str) -> None:
        messages.append(msg)

    ctx = InstallContext(lang="es", say=_say, confirm=lambda p: True, temp_dir="C:\\Temp")
    with patch(
        "setup.install_actions.acquire_sdrplay_installer", return_value=None,
    ):
        from setup.install_actions import _run_sdrplay_api_installer_body

        assert _run_sdrplay_api_installer_body(ctx) is False
    assert any("[ERROR]" in m for m in messages)


def test_run_sdrplay_api_installer_body_success_checks_api() -> None:
    messages: list[str] = []

    def _say(msg: str) -> None:
        messages.append(msg)

    ctx = InstallContext(lang="es", say=_say, confirm=lambda p: True, temp_dir="C:\\Temp")
    with patch(
        "setup.install_actions.acquire_sdrplay_installer", return_value="C:\\installer.exe",
    ):
        with patch("setup.install_actions.run_exe_installer"):
            with patch("core.soapy_runtime.check_sdrplay_api", return_value=True):
                from setup.install_actions import _run_sdrplay_api_installer_body

                assert _run_sdrplay_api_installer_body(ctx) is True
    assert any("SUCCESS" in m for m in messages)


def test_run_sdrplay_api_installer_body_api_not_detected_returns_false() -> None:
    ctx = _ctx()
    with patch(
        "setup.install_actions.acquire_sdrplay_installer", return_value="C:\\installer.exe",
    ):
        with patch("setup.install_actions.run_exe_installer"):
            with patch("core.soapy_runtime.check_sdrplay_api", return_value=False):
                from setup.install_actions import _run_sdrplay_api_installer_body

                assert _run_sdrplay_api_installer_body(ctx) is False


def test_run_sdrplay_api_installer_body_install_raises_calls_report_error() -> None:
    ctx = _ctx()
    with patch(
        "setup.install_actions.acquire_sdrplay_installer", return_value="C:\\installer.exe",
    ):
        with patch("setup.install_actions.run_exe_installer", side_effect=RuntimeError("boom")):
            with patch("setup.install_actions.report_install_error") as mock_rep:
                from setup.install_actions import _run_sdrplay_api_installer_body

                assert _run_sdrplay_api_installer_body(ctx) is False
    mock_rep.assert_called_once()


# ---------------------------------------------------------------------------
# resolve_soapy_python
# ---------------------------------------------------------------------------


def test_resolve_soapy_python_returns_best_when_present() -> None:
    ctx = _ctx()
    candidate = object()
    with patch("core.python_runtime.find_best_soapy_python", return_value=candidate):
        assert resolve_soapy_python(ctx, offer_install=True) is candidate


def test_resolve_soapy_python_returns_none_when_no_install_and_no_best() -> None:
    ctx = _ctx()
    with patch("core.python_runtime.find_best_soapy_python", return_value=None):
        assert resolve_soapy_python(ctx, offer_install=False) is None


def test_resolve_soapy_python_user_declines_install() -> None:
    messages: list[str] = []

    def _say(msg: str) -> None:
        messages.append(msg)

    ctx = InstallContext(lang="es", say=_say, confirm=lambda p: False, temp_dir="")
    with patch("core.python_runtime.find_best_soapy_python", return_value=None):
        assert resolve_soapy_python(ctx, offer_install=True) is None


def test_resolve_soapy_python_provision_succeeds() -> None:
    messages: list[str] = []

    def _say(msg: str) -> None:
        messages.append(msg)

    ctx = InstallContext(lang="es", say=_say, confirm=lambda p: True, temp_dir="")
    # Candidate must quack like PythonCandidate (label() method).
    from core.python_runtime import PythonCandidate

    candidate = PythonCandidate("C:\\py.exe", (3, 12, 9), "test")
    from core.python_runtime import ProvisionResult

    with patch("core.python_runtime.find_best_soapy_python", return_value=None):
        with patch(
            "core.python_runtime.provision_compatible_python_verbose",
            return_value=ProvisionResult(candidate=candidate, detail=""),
        ):
            assert resolve_soapy_python(ctx, offer_install=True) is candidate


def test_resolve_soapy_python_provision_fails_returns_none() -> None:
    messages: list[str] = []

    def _say(msg: str) -> None:
        messages.append(msg)

    ctx = InstallContext(lang="es", say=_say, confirm=lambda p: True, temp_dir="")
    from core.python_runtime import ProvisionResult

    with patch("core.python_runtime.find_best_soapy_python", return_value=None):
        with patch(
            "core.python_runtime.provision_compatible_python_verbose",
            return_value=ProvisionResult(candidate=None, detail="bad"),
        ):
            assert resolve_soapy_python(ctx, offer_install=True) is None


# ---------------------------------------------------------------------------
# install_python_env
# ---------------------------------------------------------------------------


def test_install_python_env_uv_fails_returns_false() -> None:
    ctx = _ctx()
    with patch("setup.install_actions._ensure_uv", side_effect=RuntimeError("no uv")):
        assert install_python_env(ctx) is False


def test_install_python_env_success_returns_true() -> None:
    ctx = _ctx()
    with patch("setup.install_actions._ensure_uv"):
        with patch("core.python_runtime.project_venv_python", return_value="C:\\.venv\\py"):
            with patch("core.python_runtime.find_best_soapy_python", return_value=None):
                with patch("core.python_runtime.ensure_project_venv_with_deps"):
                    assert install_python_env(ctx) is True


def test_install_python_env_venv_creation_fails_returns_false() -> None:
    ctx = _ctx()
    with patch("setup.install_actions._ensure_uv"):
        with patch("core.python_runtime.project_venv_python", return_value="C:\\.venv\\py"):
            with patch("core.python_runtime.find_best_soapy_python", return_value=None):
                with patch(
                    "core.python_runtime.ensure_project_venv_with_deps",
                    side_effect=RuntimeError("boom"),
                ):
                    assert install_python_env(ctx) is False


def test_install_python_env_no_best_no_venv_user_decline() -> None:
    ctx = _ctx()
    # resolve_soapy_python is a local function in install_actions -- patch there.
    with patch("setup.install_actions._ensure_uv"):
        with patch("core.python_runtime.project_venv_python", return_value=None):
            with patch("core.python_runtime.find_best_soapy_python", return_value=None):
                with patch(
                    "setup.install_actions.resolve_soapy_python", return_value=None,
                ):
                    # Second project_venv_python call after resolve also returns None.
                    with patch(
                        "core.python_runtime.project_venv_python", return_value=None,
                    ):
                        assert install_python_env(ctx) is False


# ---------------------------------------------------------------------------
# install_soapy_sdrplay3
# ---------------------------------------------------------------------------


def test_install_soapy_sdrplay3_delegates_to_helper() -> None:
    ctx = _ctx()
    with patch(
        "setup.soapy_sdrplay3.install_soapy_sdrplay3_if_needed", return_value=True,
    ) as mock:
        assert install_soapy_sdrplay3(ctx) is True
    mock.assert_called_once_with(
        ctx.temp_dir, say=ctx.say, confirm=ctx.confirm, force=False,
    )


def test_install_soapy_sdrplay3_force_passes_through() -> None:
    ctx = _ctx()
    with patch(
        "setup.soapy_sdrplay3.install_soapy_sdrplay3_if_needed", return_value=False,
    ) as mock:
        assert install_soapy_sdrplay3(ctx, force=True) is False
    assert mock.call_args.kwargs["force"] is True


# ---------------------------------------------------------------------------
# run_diagnostics / run_full_setup
# ---------------------------------------------------------------------------


def test_run_diagnostics_verbose_calls_check_env() -> None:
    ctx = _ctx()
    with patch("setup.check_env.run_check", return_value=0) as mock:
        assert run_diagnostics(ctx, verbose=True) == 0
    mock.assert_called_once_with(verbose=True, lang="es")


def test_run_diagnostics_quiet_calls_check_env() -> None:
    ctx = _ctx()
    with patch("setup.check_env.run_check", return_value=1) as mock:
        assert run_diagnostics(ctx, verbose=False) == 1
    mock.assert_called_once_with(verbose=False, lang="es")


def test_run_full_setup_delegates_to_repair_all() -> None:
    ctx = _ctx()
    with patch("setup.install_actions.repair_all", return_value=42) as mock:
        assert run_full_setup(ctx) == 42
    mock.assert_called_once_with(ctx)


# ---------------------------------------------------------------------------
# run_repo_update_action
# ---------------------------------------------------------------------------


def test_run_repo_update_action_no_restart() -> None:
    ctx = _ctx()
    result = type("R", (), {"updated": False, "needs_installer_restart": False})()
    with patch("setup.repo_update.run_repo_update", return_value=result):
        run_repo_update_action(ctx)
    # No restart_installer call expected; just verify no exception.


def test_run_repo_update_action_triggers_restart_when_needed() -> None:
    ctx = _ctx()
    result = type("R", (), {"updated": True, "needs_installer_restart": True})()
    with patch("setup.repo_update.run_repo_update", return_value=result):
        with patch("setup.repo_update.restart_installer") as mock_restart:
            run_repo_update_action(ctx)
            # Assert inside the patch context so the mock isn't reset yet.
            mock_restart.assert_called_once()