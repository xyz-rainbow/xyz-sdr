"""
xyz-sdr | setup/install_splash.py
Splash de apertura y cierre del instalador (misma barra que main.py / TUI).
"""

from __future__ import annotations

from setup.env_state import EnvironmentState, probe_environment
from setup.windows_installers import refresh_windows_environment


def _phase(logs: list[str], label: str) -> None:
    logs.append(f"Fase: {label}")


def run_installer_opening_splash(lang: str) -> EnvironmentState:
    """Banner + barra de progreso mientras se prepara el entorno del instalador."""
    from core.startup_io import suppress_soapy_probe_output, suppress_startup_output
    from tui.splash import run_startup_splash

    startup_logs: list[str] = []

    def work() -> EnvironmentState:
        _phase(startup_logs, "config")
        refresh_windows_environment()
        _phase(startup_logs, "enumerate SDR")
        with suppress_soapy_probe_output():
            with suppress_startup_output(startup_logs):
                state = probe_environment(
                    bootstrap_soapy=True, quiet_soapy=True, inprocess_soapy=False
                )
        _phase(startup_logs, "listo")
        return state

    return run_startup_splash(
        work,
        min_duration_s=0.7,
        step_sleep_s=0.1,
        redraw_interval_s=0.2,
        status_lines=startup_logs,
    )


def run_installer_closing_splash() -> None:
    """Outro con fade del banner y barra de cierre (igual que main.py)."""
    from tui.splash import print_shutdown_splash

    print_shutdown_splash()
