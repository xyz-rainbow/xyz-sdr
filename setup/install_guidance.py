"""Motor de recomendaciones del instalador (next_action)."""

from __future__ import annotations

from dataclasses import dataclass

from setup.env_state import EnvironmentState
from setup.install_i18n import t

INSTALL_BLOCKER_ORDER = (
    "pothos",
    "pothos_path",
    "sdrplay_api",
    "venv",
    "python_libs",
    "soapysdr",
)


@dataclass(frozen=True)
class InstallAction:
    id: str
    menu_highlight: str
    title_key: str
    reason_key: str
    blockers: tuple[str, ...] = ()


def _first_install_blocker(state: EnvironmentState) -> str | None:
    blockers = set(state.install_blockers)
    for key in INSTALL_BLOCKER_ORDER:
        if key in blockers:
            return key
    return None


def next_action(state: EnvironmentState, lang: str) -> InstallAction:
    blocker = _first_install_blocker(state)
    if blocker == "pothos":
        return InstallAction("repair_all", "1", "menu_repair_all", "next_reason_pothos", (blocker,))
    if blocker == "pothos_path":
        return InstallAction("repair_all", "1", "menu_repair_all", "next_reason_pothos_path", (blocker,))
    if blocker == "sdrplay_api":
        return InstallAction("repair_all", "1", "menu_repair_all", "next_reason_sdrplay", (blocker,))
    if blocker in ("venv", "python_libs", "soapysdr"):
        return InstallAction("repair_all", "1", "menu_repair_all", "next_reason_python", (blocker,))

    if state.env_ready and not state.has_devices:
        return InstallAction("run_sim", "2", "menu_run_app", "next_reason_connect_sdr", ())

    if state.env_ready:
        return InstallAction("run_app", "2", "menu_run_app", "next_reason_run", ())

    return InstallAction("repair_all", "1", "menu_repair_all", "next_reason_pending", tuple(state.install_blockers))


def format_action(state: EnvironmentState, lang: str) -> tuple[InstallAction, str, str]:
    action = next_action(state, lang)
    title = t(lang, action.title_key)
    reason = t(lang, action.reason_key)
    return action, title, reason


def drivers_row_status(state: EnvironmentState, lang: str) -> str:
    if state.drivers_ready:
        return t(lang, "status_row_ok")
    missing: list[str] = []
    if not state.sdrplay_ok:
        missing.append("SDRplay")
    if not state.pothos_installed:
        missing.append("PothosSDR")
    elif not state.path_ok:
        missing.append("PATH")
    return t(lang, "status_row_fail").format(", ".join(missing) if missing else "?")


def python_row_status(state: EnvironmentState, lang: str) -> str:
    if state.python_env_ready:
        return t(lang, "status_row_ok")
    if not state.venv_ok:
        return t(lang, "status_row_fail").format(".venv")
    if state.python_libs_missing:
        return t(lang, "status_row_fail").format(", ".join(state.python_libs_missing))
    if not state.soapy_import_ok:
        return t(lang, "status_row_fail").format("SoapySDR")
    return t(lang, "status_row_warn").format(".venv")


def hardware_row_status(state: EnvironmentState, lang: str) -> str:
    if state.has_devices:
        return t(lang, "status_row_ok_devices").format(state.device_count)
    if state.env_ready:
        return t(lang, "status_row_no_device")
    return t(lang, "status_row_hw_pending")
