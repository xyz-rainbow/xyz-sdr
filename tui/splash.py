"""
xyz-sdr | tui/splash.py
Pantallas de transición ASCII para arranque y cierre de la TUI.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from core.console_utf8 import configure_console_encoding

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

configure_console_encoding()

BANNER_LINES_ASCII = [
    "######   ##  ##  ##   ##  #######             ####### ######  ######  ######",
    "##===    ### ##   ### ##   ===###  ######### ##===== ##==== ##==== ##=== ##",
    "##        #####    ####     ###    ========= ####### ##  ## ######     ##",
    "##        ## ##     ##      ###   ######### =====## ##  ## ##====     ##",
    "######   ##  ##    ##      #######            ####### ###### ##  ## ######",
    "=======  ==  ==    ==      =======            ======= ====== ==  == ======",
    "-------------------------------------------------------------------------------",
]

BANNER_LINES = [
    "██████╗  ██╗  ██╗ ██╗   ██╗ ███████╗            ███████╗ ██████╗  ██████╗  ██████╗",
    "██╔═══╝  ╚██╗██╔╝ ╚██╗ ██╔╝ ╚══███╔╝ █████████╗ ██╔════╝ ██╔══██╗ ██╔══██╗ ╚═══██║",
    "██║       ╚███╔╝   ╚████╔╝     ███╔╝ ╚════════╝ ███████╗ ██║  ██║ ██████╔╝     ██║",
    "██║       ██╔██╗    ╚██╔╝     ███╔╝  █████████╗ ╚════██║ ██║  ██║ ██╔══██╗     ██║",
    "██████╗  ██╔╝ ██╗    ██║     ███████╗            ███████║ ██████╔╝ ██║  ██║ ██████║",
    "╚═════╝  ╚═╝  ╚═╝    ╚═╝     ╚══════╝            ╚══════╝ ╚═════╝  ╚═╝  ╚═╝ ╚═════╝",
    "─────────────────────────────────────────────────────────────────────────────────────────",
]

BANNER_COLORS = [
    "\033[91m",
    "\033[38;5;208m",
    "\033[92m",
    "\033[96m",
    "\033[95m",
    "\033[38;5;205m",
    "\033[96m",
]

C_RESET = "\033[0m"
C_CYAN = "\033[96m"
C_LIME = "\033[92m"
C_DIM = "\033[2m"
C_HIDE = "\033[38;5;232m"

SHUTDOWN_LABEL = " xyz-rainbow_technology xyz-rainbow 2026"
SHUTDOWN_TM = f"{C_DIM}tm{C_RESET}"

_USE_UNICODE_SPLASH = True


def _splash_lines() -> list[str]:
    return BANNER_LINES if _USE_UNICODE_SPLASH else BANNER_LINES_ASCII


def _progress_fill_chars() -> tuple[str, str]:
    if _USE_UNICODE_SPLASH:
        return "█", "░"
    return "#", "."

_T = TypeVar("_T")

# FD de consola real; no se redirige con suppress_startup_output (dup2 solo toca fd 1/2).
_CONSOLE_FD: int | None = None


def _get_console_fd() -> int:
    global _CONSOLE_FD
    if _CONSOLE_FD is None:
        _CONSOLE_FD = os.dup(1)
    return _CONSOLE_FD


def _term_size() -> tuple[int, int]:
    try:
        size = os.get_terminal_size()
        return size.columns, size.lines
    except OSError:
        return 80, 24


def _console_write(text: str) -> None:
    """Escribe en la TTY real aunque fd 1/2 estén redirigidos durante el arranque."""
    payload = text.encode("utf-8", errors="replace")
    try:
        os.write(_get_console_fd(), payload)
    except OSError:
        sys.__stdout__.write(text)
        sys.__stdout__.flush()


def _handoff_to_textual() -> None:
    """Restaura stdout/stderr antes de que Textual tome el control."""
    from core.console_utf8 import prepare_terminal_for_tui

    prepare_terminal_for_tui()


def _clear_screen() -> None:
    _console_write("\033[2J\033[H")


def _restore_terminal() -> None:
    from core.console_utf8 import restore_terminal_after_tui

    restore_terminal_after_tui()


def _banner_layout(width: int, height: int) -> tuple[int, list[str]]:
    lines = _splash_lines()
    v_padding = max(0, (height - len(lines) - 4) // 2)
    centered: list[str] = []
    for line in lines:
        pad = max(0, (width - len(line)) // 2)
        centered.append(" " * pad + line)
    return v_padding, centered


def _render_banner_block(
    centered_lines: list[str],
    v_padding: int,
    *,
    line_opacity: list[float] | None = None,
) -> str:
    if line_opacity is None:
        line_opacity = [1.0] * len(_splash_lines())

    lines = _splash_lines()
    colors = BANNER_COLORS[: len(lines)]
    out: list[str] = ["\n" * v_padding]
    for line, color, opacity in zip(centered_lines, colors, line_opacity):
        if opacity <= 0.0:
            continue
        if opacity >= 1.0:
            out.append(f"{color}{line}{C_RESET}")
        elif opacity < 0.35:
            out.append(f"{C_HIDE}{line}{C_RESET}")
        else:
            out.append(f"{C_DIM}{color}{line}{C_RESET}")
    out.append("")
    return "\n".join(out)


def _draw_progress_bar(
    width: int,
    percent: int,
    bar_width: int = 40,
    *,
    use_cr: bool = True,
) -> None:
    bar_pad = max(0, (width - bar_width - 8) // 2)
    filled = int((percent / 100) * bar_width)
    empty = bar_width - filled
    bar_color = C_CYAN if percent < 50 else C_LIME
    fill_ch, empty_ch = _progress_fill_chars()
    bar = fill_ch * filled + empty_ch * empty
    prefix = "\r" if use_cr else ""
    _console_write(
        prefix
        + " " * bar_pad
        + f"{C_RESET}[{bar_color}{bar}{C_RESET}] {percent:3d}%"
    )


def _trim_status_line(line: str, width: int) -> str:
    plain = line.strip()
    if len(plain) <= width - 2:
        return plain
    return plain[: max(8, width - 5)] + "..."


_SPLASH_NOISE_MARKERS = (
    "SOAPY plugin path",
    "Soapy bundled runtime",
    "core.soapy_runtime",
    ":\\",
    "/",
)


def _is_splash_noise_line(line: str) -> bool:
    plain = line.strip()
    if not plain:
        return True
    if plain.startswith("Fase:"):
        return False
    lowered = plain.lower()
    return any(marker.lower() in lowered for marker in _SPLASH_NOISE_MARKERS)


def _splash_display_lines(status_lines: list[str] | None) -> list[str]:
    if not status_lines:
        return []
    phases = [line.strip() for line in status_lines if line.strip().startswith("Fase:")]
    if phases:
        latest = phases[-1].removeprefix("Fase:").strip()
        if latest.lower() == "listo":
            return ["Listo"]
        return [f"Cargando: {latest}…"]
    clean = [line.strip() for line in status_lines if not _is_splash_noise_line(line)]
    return clean[-1:]


def _phase_progress_window(status_lines: list[str] | None) -> tuple[int, int] | None:
    """Rango de % para la fase actual (mín, máx)."""
    if not status_lines:
        return None
    phase = ""
    for line in reversed(status_lines):
        text = line.strip()
        if text.startswith("Fase:"):
            phase = text
            break
    if not phase:
        return None
    lowered = phase.lower()
    if "listo" in lowered or "ready" in lowered:
        return 100, 100
    if "recovery" in lowered or "api" in lowered:
        return 80, 95
    if "enumerate" in lowered:
        return 45, 78
    if "config" in lowered:
        return 15, 40
    return None


def _splash_progress_percent(
    elapsed_s: float,
    status_lines: list[str] | None,
    *,
    thread_alive: bool,
) -> int:
    if not thread_alive:
        return 100
    window = _phase_progress_window(status_lines)
    time_progress = min(98, int((elapsed_s / 0.6) * 98))
    if window is None:
        return time_progress
    lo, hi = window
    if lo >= hi:
        return lo
    span = hi - lo
    creep = int(span * min(1.0, elapsed_s / 20.0))
    return min(hi, lo + max(creep, 0))


def _render_startup_frame(
    width: int,
    v_padding: int,
    centered: list[str],
    percent: int,
    status_lines: list[str] | None,
    *,
    max_status_lines: int = 3,
    full_clear: bool = True,
) -> None:
    if full_clear:
        _clear_screen()
    else:
        _console_write("\033[H")
    _console_write(_render_banner_block(centered, v_padding))
    _draw_progress_bar(width, percent, use_cr=False)
    display_lines = _splash_display_lines(status_lines)
    if display_lines:
        _console_write("\n")
        for line in display_lines[-max_status_lines:]:
            display = _trim_status_line(line, width)
            pad = max(0, (width - len(display)) // 2)
            _console_write(" " * pad + f"{C_DIM}{display}{C_RESET}\033[K\n")
        _console_write("\033[J")


def run_startup_splash(
    work: Callable[[], _T],
    *,
    min_duration_s: float = 0.6,
    step_sleep_s: float = 0.12,
    redraw_interval_s: float = 0.25,
    status_lines: list[str] | None = None,
) -> _T:
    """
    Muestra banner + barra de progreso mientras ``work()`` corre en segundo plano.
    La salida de consola del trabajo debe suprimirse con ``suppress_startup_output``.
    Si ``status_lines`` se proporciona, las últimas líneas se muestran bajo la barra.

    Redibuja como máximo cada ``redraw_interval_s`` (o al cambiar % / líneas de estado)
    para no inundar la terminal con secuencias de pantalla completa.
    """
    global _USE_UNICODE_SPLASH
    _USE_UNICODE_SPLASH = configure_console_encoding()

    width, height = _term_size()
    v_padding, centered = _banner_layout(width, height)

    result: list[_T] = []
    error: list[BaseException] = []

    def _runner() -> None:
        try:
            result.append(work())
        except BaseException as exc:  # noqa: BLE001
            error.append(exc)

    _render_startup_frame(width, v_padding, centered, 0, status_lines, full_clear=True)

    thread = threading.Thread(target=_runner, name="xyz-sdr-startup", daemon=True)
    t0 = time.monotonic()
    thread.start()

    percent = 0
    last_drawn_percent = 0
    last_status_len = len(status_lines) if status_lines else 0
    last_redraw_at = time.monotonic()

    while True:
        elapsed = time.monotonic() - t0
        percent = _splash_progress_percent(
            elapsed,
            status_lines,
            thread_alive=thread.is_alive(),
        )

        status_len = len(status_lines) if status_lines else 0
        now = time.monotonic()
        should_redraw = (
            percent != last_drawn_percent
            or status_len != last_status_len
            or (now - last_redraw_at) >= redraw_interval_s
        )
        if should_redraw:
            _render_startup_frame(
                width,
                v_padding,
                centered,
                percent,
                status_lines,
                full_clear=False,
            )
            last_drawn_percent = percent
            last_status_len = status_len
            last_redraw_at = now

        if not thread.is_alive():
            break

        time.sleep(step_sleep_s)

    thread.join()
    _render_startup_frame(width, v_padding, centered, 100, status_lines, full_clear=False)
    _console_write("\n")
    time.sleep(0.15)
    _handoff_to_textual()

    if error:
        raise error[0]
    return result[0]


def print_startup_splash() -> None:
    """Banner centrado y barra de progreso de arranque (solo visual, sin trabajo)."""
    run_startup_splash(lambda: None, min_duration_s=1.2)


def print_shutdown_splash() -> None:
    """Transición a fondo negro, fade-in del banner y barra de cierre con branding."""
    global _USE_UNICODE_SPLASH
    _USE_UNICODE_SPLASH = configure_console_encoding()

    width, height = _term_size()
    v_padding, centered = _banner_layout(width, height)

    fade_steps = 18
    line_stagger = 2.2

    for step in range(1, fade_steps + 1):
        _clear_screen()
        opacities: list[float] = []
        for i in range(len(_splash_lines())):
            progress = (step - i * line_stagger) / (fade_steps - len(_splash_lines()) * 0.4)
            opacities.append(max(0.0, min(1.0, progress)))

        _console_write(_render_banner_block(centered, v_padding, line_opacity=opacities))
        time.sleep(0.045)

    label_visible = f"{SHUTDOWN_LABEL}{SHUTDOWN_TM}"
    bracket_pad = max(0, (width - len(label_visible) - 2) // 2)
    steps = 24

    for i in range(steps + 1):
        progress = i / steps
        reveal = int(progress * len(SHUTDOWN_LABEL))
        visible = SHUTDOWN_LABEL[:reveal]
        hidden = SHUTDOWN_LABEL[reveal:]
        dim_hidden = "".join(_progress_fill_chars()[1] if ch != " " else " " for ch in hidden)

        tm_suffix = SHUTDOWN_TM if reveal >= len(SHUTDOWN_LABEL) else ""

        bar_color = C_CYAN if progress < 0.55 else C_LIME
        line = (
            f"{C_RESET}[{bar_color}{visible}{C_DIM}{dim_hidden}{C_RESET}"
            f"{tm_suffix}{C_RESET}]"
        )

        _console_write("\033[H")
        _console_write(_render_banner_block(centered, v_padding))
        _console_write(" " * bracket_pad + line + "\n")
        time.sleep(0.05)

    time.sleep(0.35)
    _restore_terminal()
    _clear_screen()


def print_crash_splash(
    *,
    log_path: str | Path | None = None,
    reason: str = "Sesión terminada de forma inesperada",
    tail_lines: int = 25,
    animate: bool = True,
) -> None:
    """Splash de cierre tras crash + resumen del log de sesión."""
    from core.session_log import tail_session_log

    global _USE_UNICODE_SPLASH
    _USE_UNICODE_SPLASH = configure_console_encoding()

    _clear_screen()
    width, height = _term_size()
    v_padding, centered = _banner_layout(width, height)
    _console_write(_render_banner_block(centered, v_padding))

    error_line = f"{C_RESET}\033[91m{reason}{C_RESET}"
    pad = max(0, (width - len(reason)) // 2)
    _console_write("\n" + " " * pad + error_line + "\n")

    log_text = ""
    if log_path:
        try:
            path = Path(log_path)
            if path.is_file():
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                log_text = "\n".join(lines[-tail_lines:])
        except OSError:
            pass
    if not log_text:
        tail = tail_session_log(tail_lines)
        log_text = "\n".join(tail)

    if log_path:
        log_msg = f"Log: {log_path}"
        _console_write(f"\n{C_DIM}{log_msg}{C_RESET}\n")

    if log_text.strip():
        _console_write(f"\n{C_DIM}--- últimas líneas del log ---{C_RESET}\n")
        for line in log_text.splitlines()[-tail_lines:]:
            _console_write(f"{C_DIM}{line}{C_RESET}\n")

    if animate:
        steps = 12
        bar_width = 40
        for i in range(steps + 1):
            percent = int(100 * i / steps)
            _draw_progress_bar(width, percent, bar_width=bar_width)
            time.sleep(0.04)
        _console_write("\n")

    _restore_terminal()
    _clear_screen()
