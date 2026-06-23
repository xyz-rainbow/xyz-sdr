"""
xyz-sdr | tui/splash.py
Pantallas de transición ASCII para arranque y cierre de la TUI.
"""

from __future__ import annotations

import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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
SHUTDOWN_TM = f"{C_DIM}ᵗᵐ{C_RESET}"


def _term_size() -> tuple[int, int]:
    try:
        size = os.get_terminal_size()
        return size.columns, size.lines
    except OSError:
        return 80, 24


def _clear_screen() -> None:
    sys.stdout.write("\033[40m\033[2J\033[H")
    sys.stdout.flush()


def _restore_terminal() -> None:
    sys.stdout.write(C_RESET)
    sys.stdout.flush()


def _banner_layout(width: int, height: int) -> tuple[int, list[str]]:
    v_padding = max(0, (height - len(BANNER_LINES) - 4) // 2)
    centered: list[str] = []
    for line in BANNER_LINES:
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
        line_opacity = [1.0] * len(BANNER_LINES)

    out: list[str] = ["\n" * v_padding]
    for line, color, opacity in zip(centered_lines, BANNER_COLORS, line_opacity):
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


def print_startup_splash() -> None:
    """Banner centrado y barra de progreso de arranque."""
    width, height = _term_size()
    v_padding, centered = _banner_layout(width, height)

    _clear_screen()
    sys.stdout.write(_render_banner_block(centered, v_padding))
    sys.stdout.flush()

    bar_width = 40
    bar_pad = max(0, (width - bar_width - 8) // 2)
    steps = 20

    for i in range(steps + 1):
        percent = int((i / steps) * 100)
        filled = int((i / steps) * bar_width)
        empty = bar_width - filled
        bar_color = C_CYAN if percent < 50 else C_LIME
        bar = "█" * filled + "░" * empty
        sys.stdout.write(
            "\r"
            + " " * bar_pad
            + f"{C_RESET}[{bar_color}{bar}{C_RESET}] {percent:3d}%"
        )
        sys.stdout.flush()
        time.sleep(0.06)

    sys.stdout.write("\n")
    sys.stdout.flush()
    time.sleep(0.2)
    _restore_terminal()


def print_shutdown_splash() -> None:
    """Transición a fondo negro, fade-in del banner y barra de cierre con branding."""
    width, height = _term_size()
    v_padding, centered = _banner_layout(width, height)

    fade_steps = 18
    line_stagger = 2.2

    for step in range(1, fade_steps + 1):
        _clear_screen()
        opacities: list[float] = []
        for i in range(len(BANNER_LINES)):
            progress = (step - i * line_stagger) / (fade_steps - len(BANNER_LINES) * 0.4)
            opacities.append(max(0.0, min(1.0, progress)))

        sys.stdout.write(_render_banner_block(centered, v_padding, line_opacity=opacities))
        sys.stdout.flush()
        time.sleep(0.045)

    label_visible = f"{SHUTDOWN_LABEL}{SHUTDOWN_TM}"
    bracket_pad = max(0, (width - len(label_visible) - 2) // 2)
    steps = 24

    for i in range(steps + 1):
        progress = i / steps
        reveal = int(progress * len(SHUTDOWN_LABEL))
        visible = SHUTDOWN_LABEL[:reveal]
        hidden = SHUTDOWN_LABEL[reveal:]
        dim_hidden = "".join("░" if ch != " " else " " for ch in hidden)

        tm_suffix = SHUTDOWN_TM if reveal >= len(SHUTDOWN_LABEL) else ""

        bar_color = C_CYAN if progress < 0.55 else C_LIME
        line = (
            f"{C_RESET}[{bar_color}{visible}{C_DIM}{dim_hidden}{C_RESET}"
            f"{tm_suffix}{C_RESET}]"
        )

        # Re-posicionar cursor bajo el banner para la barra de cierre
        sys.stdout.write("\033[H")
        sys.stdout.write(_render_banner_block(centered, v_padding))
        sys.stdout.write(" " * bracket_pad + line + "\n")
        sys.stdout.flush()
        time.sleep(0.05)

    time.sleep(0.35)
    _restore_terminal()
    _clear_screen()
