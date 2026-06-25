"""
xyz-sdr | setup/install_sdrplay_api.py
Instala solo SDRplay API v3.15 (atajo desde la raíz del repo).
"""

from __future__ import annotations

import os
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_script_dir, ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
os.chdir(_project_root)

from pathlib import Path

from core.runtime_paths import configure_pycache_prefix

configure_pycache_prefix(Path(_project_root))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from setup.install_actions import InstallContext, run_sdrplay_api_installer
from setup.install_i18n import detect_system_language, t
from setup.install_log import get_install_logger, log_line
from setup.windows_installers import refresh_windows_environment


def _say(message: str) -> None:
    print(message, flush=True)
    log_line(message)


def main() -> int:
    get_install_logger()
    refresh_windows_environment()
    lang = detect_system_language()
    temp_dir = os.environ.get("TEMP", os.environ.get("TMP", "."))

    _say(f"\n=== {t(lang, 'menu_opt_sdrplay')} ===\n")

    ctx = InstallContext(lang=lang, say=_say, confirm=lambda _p: True, temp_dir=temp_dir)
    ok = run_sdrplay_api_installer(ctx)
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[CANCELLED]")
        sys.exit(130)
