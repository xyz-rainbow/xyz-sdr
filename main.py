"""
xyz-sdr | main.py
Punto de entrada principal. Lanza la TUI o el modo CLI.
"""

from __future__ import annotations

import os
import sys

_ROOT = __import__("pathlib").Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.runtime_paths import configure_pycache_prefix

configure_pycache_prefix(_ROOT)

import argparse
import logging

# Forzar salida UTF-8 en Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("xyz-sdr")


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
    if args.sim:
        driver = "simulated"
    else:
        from core.soapy_runtime import bootstrap_soapy, format_hardware_help
        from core.device import resolve_device

        status = bootstrap_soapy()
        has_hardware = status.import_ok and status.has_devices

        if not has_hardware:
            help_text = format_hardware_help(status)
            if not status.import_ok:
                print("SoapySDR no disponible en Python (bindings/DLL/PATH).")
            else:
                print("SoapySDR OK pero no se detectó ningún dispositivo SDR conectado.")
            if help_text:
                print(help_text)
            print("\nConfigura el entorno: .\\setup\\install_drivers.ps1 → opción 3")
            print("Ejecuta la app: .\\scripts\\run.ps1")
            print("Pruebas sin hardware (opcional): .\\scripts\\run.ps1 --sim")
            sys.exit(1)
        elif driver in ("auto", ""):
            try:
                kwargs = resolve_device("auto", status.devices)
                driver = str(kwargs.get("driver", driver))
            except Exception:
                pass

    logger.info(f"Iniciando xyz-sdr | driver={driver} freq={center_freq/1e6:.3f}MHz mode={demod_mode}")

    # ── Lanzar TUI ─────────────────────────────────────────────────────────
    try:
        from tui.app import XyzSDRApp
        from tui.splash import print_startup_splash, print_shutdown_splash
        from core.device import HardwareInitializationError
        app = XyzSDRApp(
            driver=driver,
            center_freq=center_freq,
            gain=gain,
            volume=volume,
            demod_mode=demod_mode,
            config=config,
            config_path=args.config,
            debug_mode=args.debug,
        )
        print_startup_splash()
        app.run()
        if app._graceful_shutdown:
            print_shutdown_splash()
    except HardwareInitializationError as e:
        logger.error(str(e))
        sys.exit(1)
    except ImportError as e:
        logger.error(f"No se pudo importar la TUI: {e}")
        logger.error("Configura el entorno: .\\setup\\install_drivers.ps1 → opción 3")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Saliendo...")
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
