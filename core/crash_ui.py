"""
xyz-sdr | core/crash_ui.py
Entrypoint mínimo para splash de crash (invocado desde run.ps1).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _map_windows_exit_code(code: int) -> str:
    if code in (3221225477, -1073741819):
        return "Native crash suspected (access violation 0xC0000005)"
    if code in (3221225725, -1073741571):
        return "Native crash suspected (stack overflow)"
    if code == 1:
        return "Python error (exit 1)"
    if code != 0:
        return f"Process exited with code {code}"
    return "Unexpected termination"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="xyz-sdr crash report UI")
    parser.add_argument("--log", default="", help="Ruta al log de sesión")
    parser.add_argument("--reason", default="", help="Motivo del crash")
    parser.add_argument("--exit-code", type=int, default=1, help="Código de salida del proceso")
    parser.add_argument("--no-splash", action="store_true", help="Solo texto, sin animación")
    parser.add_argument("--tail", type=int, default=25, help="Líneas del log a mostrar")
    args = parser.parse_args(argv)

    reason = args.reason.strip() or _map_windows_exit_code(args.exit_code)
    log_path = args.log.strip() or None

    try:
        from tui.splash import print_crash_splash

        print_crash_splash(
            log_path=log_path,
            reason=reason,
            tail_lines=args.tail,
            animate=not args.no_splash,
        )
    except Exception as exc:
        print(f"\n[ERROR] xyz-sdr terminó de forma inesperada: {reason}", file=sys.stderr)
        if log_path and Path(log_path).is_file():
            print(f"Log: {log_path}", file=sys.stderr)
            try:
                lines = Path(log_path).read_text(encoding="utf-8", errors="replace").splitlines()
                for line in lines[-args.tail :]:
                    print(line, file=sys.stderr)
            except OSError:
                pass
        print(f"(splash error: {exc})", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
