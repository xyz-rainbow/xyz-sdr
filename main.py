"""
xyz-sdr | main.py
Punto de entrada principal. Lanza la TUI o el modo CLI.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_pycache = _ROOT / "var" / "pycache"
_pycache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("PYTHONPYCACHEPREFIX", str(_pycache))

from core.runtime_paths import configure_pycache_prefix

configure_pycache_prefix(_ROOT)

from core.console_utf8 import configure_console_encoding, prepare_terminal_for_tui
from core.logging_config import detach_console_logging

configure_console_encoding()

import argparse
import logging

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("xyz-sdr")


class StartupHardwareError(Exception):
    """Sin hardware Soapy tras bootstrap; mensajes para consola."""

    def __init__(self, lines: list[str]):
        self.lines = lines
        super().__init__("\n".join(lines))


def parse_args():
    parser = argparse.ArgumentParser(
        prog="xyz-sdr",
        description="🛰️  xyz-sdr — Terminal SDR Controller con IA",
    )
    parser.add_argument("--driver",   default=None, help="Driver SDR (auto, sdrplay, rtlsdr, hackrf...)")
    parser.add_argument("--freq",     type=float, default=None, help="Frecuencia inicial en MHz")
    parser.add_argument("--gain",     type=float, default=None, help="Ganancia en dB")
    parser.add_argument("--mode",     default=None, choices=["wbfm","nbfm","am","usb","lsb"], help="Modo de demodulación")
    parser.add_argument("--sim",      action="store_true", help="Forzar modo simulación (sin hardware)")
    parser.add_argument("--allow-system-python", action="store_true",
                        help="No exige .venv (solo desarrollo)")
    parser.add_argument("--check",    action="store_true", help="Verificar entorno y salir")
    parser.add_argument("--list-dev", action="store_true", help="Listar dispositivos y salir")
    parser.add_argument("--config",   default="config/defaults.toml", help="Ruta al archivo de configuración")
    parser.add_argument("--debug",    action="store_true", help="Activa logs de depuración e instrumentación en el panel")
    parser.add_argument("--no-splash", action="store_true", help="Omitir pantalla de carga (depuración TUI)")
    return parser.parse_args()


def load_config(path: str) -> dict:
    """Carga la configuración TOML."""
    try:
        if sys.version_info >= (3, 11):
            import tomllib
        else:
            import tomli as tomllib

        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        logger.warning(f"Config no encontrada: {path}. Usando valores por defecto.")
        return {}
    except Exception as e:
        logger.error(f"Error leyendo config: {e}")
        return {}


def main():
    args = parse_args()

    # Re-lanzar con .venv / Python compatible (mismo entorno con o sin --sim)
    if not os.environ.get("XYZ_SDR_REEXEC_DONE"):
        try:
            from core.python_runtime import try_reexec_for_soapy
            try_reexec_for_soapy()
        except Exception as exc:
            logger.debug("Re-exec omitido: %s", exc)

    if not args.allow_system_python:
        from core.python_runtime import ensure_project_venv_or_exit
        ensure_project_venv_or_exit()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)

    config = load_config(args.config)

    # ── Modo check ──────────────────────────────────────────────────────────
    if args.check:
        from setup.check_env import run_check
        sys.exit(run_check())

    # ── Listar dispositivos ─────────────────────────────────────────────────
    if args.list_dev:
        from core.soapy_runtime import bootstrap_soapy, format_hardware_help

        status = bootstrap_soapy()
        if not status.import_ok:
            print("SoapySDR no disponible en Python.")
            help_text = format_hardware_help(status)
            if help_text:
                print(help_text)
            sys.exit(1)

        from core.device import SDRDevice

        devices = SDRDevice.list_devices()
        real = [d for d in devices if d.get("driver") != "simulated"]
        if not real:
            print("SoapySDR OK pero no hay dispositivos conectados.")
            print("  Prueba: SoapySDRUtil --find=driver=sdrplay")
            sys.exit(1)

        print(f"Dispositivos encontrados: {len(real)}")
        for i, d in enumerate(real):
            print(f"  [{i}] {d}")
        sys.exit(0)

    # ── Configuración combinada (TOML + args CLI) ───────────────────────────
    dev_cfg = config.get("device", {})
    driver      = args.driver or dev_cfg.get("driver", "sdrplay")
    center_freq = (args.freq * 1e6) if args.freq else dev_cfg.get("center_freq", 100_600_000)
    gain        = args.gain if args.gain is not None else dev_cfg.get("gain", 40.0)
    demod_mode  = args.mode or config.get("dsp", {}).get("demod_mode", "wbfm")
    volume      = config.get("dsp", {}).get("volume", 75.0)

    # ── Verificación de hardware real y simulación ─────────────────────────
    startup_logs: list[str] = []

    if args.sim:
        driver = "simulated"

    # ── Lanzar TUI ─────────────────────────────────────────────────────────
    try:
        from core.startup_io import suppress_startup_output
        from tui.app import XyzSDRApp
        from tui.splash import print_shutdown_splash, run_startup_splash
        from core.device import HardwareInitializationError

        def _startup_phase() -> None:
            nonlocal driver
            if not args.sim:
                from core.soapy_runtime import bootstrap_soapy, format_hardware_help
                from core.device import resolve_device

                with suppress_startup_output(startup_logs):
                    status = bootstrap_soapy()
                has_hardware = status.import_ok and status.has_devices

                if not has_hardware:
                    lines: list[str] = []
                    if not status.import_ok:
                        lines.append("SoapySDR no disponible en Python (bindings/DLL/PATH).")
                    else:
                        lines.append("SoapySDR OK pero no se detectó ningún dispositivo SDR conectado.")
                    help_text = format_hardware_help(status)
                    if help_text:
                        lines.append(help_text)
                    lines.append("")
                    lines.append("Configura el entorno: .\\setup\\install_drivers.ps1 → opción 3")
                    lines.append("Ejecuta la app: .\\scripts\\run.ps1")
                    lines.append("Pruebas sin hardware (opcional): .\\scripts\\run.ps1 --sim")
                    raise StartupHardwareError(lines)

                if driver in ("auto", ""):
                    try:
                        with suppress_startup_output(startup_logs):
                            kwargs = resolve_device("auto", status.devices)
                        driver = str(kwargs.get("driver", driver))
                    except Exception:
                        pass

            with suppress_startup_output(startup_logs):
                logger.info(
                    "Iniciando xyz-sdr | driver=%s freq=%.3fMHz mode=%s",
                    driver,
                    center_freq / 1e6,
                    demod_mode,
                )

        if args.no_splash:
            _startup_phase()
        else:
            run_startup_splash(_startup_phase)

        prepare_terminal_for_tui()
        detach_console_logging()

        app = XyzSDRApp(
            driver=driver,
            center_freq=center_freq,
            gain=gain,
            volume=volume,
            demod_mode=demod_mode,
            config=config,
            config_path=args.config,
            debug_mode=args.debug,
            startup_logs=startup_logs,
        )
        app.run()
        if app._graceful_shutdown and not args.no_splash:
            print_shutdown_splash()
    except StartupHardwareError as exc:
        for line in exc.lines:
            print(line)
        sys.exit(1)
    except HardwareInitializationError as e:
        logger.error(str(e))
        sys.exit(1)
    except ImportError as e:
        logger.error(f"No se pudo importar la TUI: {e}")
        logger.error("Configura el entorno: .\\setup\\install_drivers.ps1 → opción 3")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Saliendo...")
        if not args.no_splash:
            try:
                from tui.splash import print_shutdown_splash
                print_shutdown_splash()
            except Exception:
                pass
    except Exception as e:
        logger.exception(f"Error fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
