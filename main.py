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

from core.runtime_paths import bootstrap_project_caches

bootstrap_project_caches(_ROOT)

from core.console_utf8 import configure_console_encoding, prepare_terminal_for_tui, register_windows_console_restore, restore_terminal_after_tui
from core.logging_config import detach_console_logging

import argparse
import atexit
import logging

configure_console_encoding()
atexit.register(restore_terminal_after_tui)
register_windows_console_restore()

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


def _will_use_startup_splash(args: argparse.Namespace) -> bool:
    """True si la TUI mostrará splash (no modos CLI ni --no-splash)."""
    return not args.no_splash and not args.check and not args.list_dev and not args.diagnose_sdrplay


def parse_args():
    parser = argparse.ArgumentParser(
        prog="xyz-sdr",
        description="🛰️  xyz-sdr — Terminal SDR Controller con IA",
    )
    parser.add_argument("--driver",   default=None, help="Driver SDR (auto, sdrplay, rtlsdr, hackrf...)")
    parser.add_argument("--freq",     type=float, default=None, help="Frecuencia inicial en MHz")
    parser.add_argument("--gain",     type=float, default=None, help="Ganancia en dB")
    parser.add_argument("--mode",     default=None,
                        choices=["wbfm", "nbfm", "am", "usb", "lsb", "cw", "dsb", "raw", "auto"],
                        help="Modo de demodulación")
    parser.add_argument("--sim",      action="store_true", help="Forzar modo simulación (sin hardware)")
    parser.add_argument("--allow-system-python", action="store_true",
                        help="No exige .venv (solo desarrollo)")
    parser.add_argument("--check",    action="store_true", help="Verificar entorno y salir")
    parser.add_argument("--list-dev", action="store_true", help="Listar dispositivos y salir")
    parser.add_argument("--config",   default="config/defaults.toml", help="Ruta al archivo de configuración")
    parser.add_argument("--band",     default=None,
                        help="Perfil de banda (config/bands/<nombre>.toml, p. ej. fm_broadcast, airband)")
    parser.add_argument("--debug",    action="store_true", help="Activa logs de depuración e instrumentación en el panel")
    parser.add_argument("--no-splash", action="store_true", help="Omitir pantalla de carga (depuración TUI)")
    parser.add_argument("--diagnose-sdrplay", action="store_true", help="Informe diagnóstico SDRplay y salir")
    parser.add_argument(
        "--no-restart-sdrplay-service",
        action="store_true",
        help="No reiniciar SDRplayAPIService tras crash de sesión anterior",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Abortar si hay errores de hardware en vez de fallback silencioso a 'simulated'",
    )
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

    from core.session_exit import clear_exit_marker, read_exit_marker, register_abnormal_atexit, write_exit_marker
    from core.session_log import close_session_log, get_session_log_path, log_breadcrumb, start_session_log

    previous_marker = read_exit_marker()
    clear_exit_marker()
    session_log_path = start_session_log()
    register_abnormal_atexit()

    if not args.no_restart_sdrplay_service and not args.sim:
        from core.sdrplay_service import maybe_restart_sdrplay_service_after_crash

        restarted, restart_msg = maybe_restart_sdrplay_service_after_crash(
            previous_marker,
            log=log_breadcrumb,
        )
        if restarted and restart_msg:
            logger.info(restart_msg)

    try:
        import faulthandler

        if session_log_path is not None:
            fault_file = open(session_log_path, "a", encoding="utf-8")
            faulthandler.enable(file=fault_file, all_threads=True)
    except Exception:
        pass

    log_breadcrumb(f"main start argv={sys.argv[1:]!r}")

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

    startup_logs: list[str] = []
    use_startup_splash = _will_use_startup_splash(args)
    defer_config = use_startup_splash

    def _load_application_config(*, exit_on_error: bool = True) -> tuple[dict, str | None]:
        cfg = load_config(args.config)
        from core.band_profiles import merge_configs
        from core.config_store import user_config_path

        local_path = user_config_path(args.config)
        if Path(local_path).is_file():
            local_cfg = load_config(local_path)
            if local_cfg:
                cfg = merge_configs(cfg, local_cfg)
                logger.info("Config local cargada: %s", local_path)

        band = args.band
        if not band:
            saved = cfg.get("app", {}).get("active_band_profile", "")
            band = str(saved).strip() or None

        if band:
            from core.band_profiles import load_band_profile
            from core.config_store import ensure_user_config, patch_app_section

            try:
                band_cfg = load_band_profile(band)
                cfg = merge_configs(cfg, band_cfg)
                logger.info("Perfil de banda activo: %s", band)
                if args.band:
                    patch_app_section(ensure_user_config(args.config), active_band_profile=args.band)
            except FileNotFoundError as exc:
                if exit_on_error:
                    logger.error("%s", exc)
                    sys.exit(1)
                raise StartupHardwareError([str(exc)]) from exc
            except Exception as exc:
                msg = f"Error cargando perfil de banda {band}: {exc}"
                if exit_on_error:
                    logger.error("%s", msg)
                    sys.exit(1)
                raise StartupHardwareError([msg]) from exc
        return cfg, band

    from core.startup_io import suppress_startup_output

    config: dict = {}
    active_band: str | None = None
    if not defer_config:
        config, active_band = _load_application_config()

    # ── Modo check ──────────────────────────────────────────────────────────
    if args.check:
        from setup.check_env import run_check

        code = run_check()
        write_exit_marker("check", log_path=session_log_path, exit_code=code)
        close_session_log()
        sys.exit(code)

    if args.diagnose_sdrplay:
        from core.diagnose_sdrplay import collect_diagnose_report, format_diagnose_report, write_diagnose_report

        report = collect_diagnose_report()
        print(format_diagnose_report(report))
        diag_path = write_diagnose_report(report)
        log_breadcrumb(f"diagnose written {diag_path}")
        code = 1 if report.issues else 0
        write_exit_marker("diagnose", log_path=session_log_path, detail=str(diag_path), exit_code=code)
        close_session_log()
        sys.exit(code)

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
        write_exit_marker("list_dev", log_path=session_log_path, exit_code=0)
        close_session_log()
        sys.exit(0)

    # ── Configuración combinada (TOML + args CLI) ───────────────────────────
    dev_cfg = config.get("device", {}) if config else {}
    driver      = args.driver or dev_cfg.get("driver", "sdrplay")
    center_freq = (args.freq * 1e6) if args.freq else dev_cfg.get("center_freq", 100_600_000)
    gain        = args.gain if args.gain is not None else dev_cfg.get("gain", 40.0)
    demod_mode  = args.mode or (config.get("dsp", {}).get("demod_mode", "wbfm") if config else "wbfm")
    volume      = config.get("dsp", {}).get("volume", 75.0) if config else 75.0

    # ── Verificación de hardware real y simulación ─────────────────────────
    if args.sim:
        driver = "simulated"

    enumerated_devices: list[dict] = []

    # ── Lanzar TUI ─────────────────────────────────────────────────────────
    try:
        from tui.app import XyzSDRApp
        from tui.splash import print_shutdown_splash, run_startup_splash
        from core.device import HardwareInitializationError

        def _startup_phase() -> None:
            nonlocal driver, enumerated_devices, config, active_band
            nonlocal center_freq, gain, demod_mode, volume

            with suppress_startup_output(startup_logs):
                if defer_config and not config:
                    loaded_cfg, loaded_band = _load_application_config(exit_on_error=False)
                    config = loaded_cfg
                    active_band = loaded_band
                    dev_cfg = config.get("device", {})
                    if not args.driver:
                        driver = str(dev_cfg.get("driver", driver))
                    if args.freq is None:
                        center_freq = float(dev_cfg.get("center_freq", center_freq))
                    if args.gain is None:
                        gain = float(dev_cfg.get("gain", gain))
                    if not args.mode:
                        demod_mode = str(config.get("dsp", {}).get("demod_mode", demod_mode))
                    volume = float(config.get("dsp", {}).get("volume", volume))

            if not args.sim:
                from core.soapy_runtime import bootstrap_soapy, format_hardware_help
                from core.device import filter_sdr_devices, resolve_device

                with suppress_startup_output(startup_logs):
                    from core.sdrplay_enumerate import recover_sdrplay_enumeration

                    found, recover_msg, _recover_status = recover_sdrplay_enumeration(
                        restart_if_missing=True,
                        log=log_breadcrumb,
                    )
                    if recover_msg:
                        log_breadcrumb(f"sdrplay.enumerate: found={found} msg={recover_msg!r}")
                    status = bootstrap_soapy(force=True)
                log_breadcrumb(
                    f"bootstrap import_ok={status.import_ok} plugin={status.sdrplay_plugin_status} "
                    f"module={status.sdrplay_plugin_module!r} devices={len(status.devices)}"
                )
                sdr_devices = filter_sdr_devices(status.devices)
                enumerated_devices = [dict(dev) for dev in sdr_devices]
                has_hardware = status.import_ok and bool(sdr_devices)

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
                            kwargs = resolve_device("auto", sdr_devices)
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
            run_startup_splash(_startup_phase, status_lines=startup_logs)

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
            band_profile=active_band,
            enumerated_devices=enumerated_devices,
            previous_session_marker=previous_marker,
            strict=args.strict,
        )
        try:
            # Textual: mouse habilitado (Windows incl.). XYZ_SDR_NO_MOUSE=1 para desactivar.
            mouse = os.environ.get("XYZ_SDR_NO_MOUSE", "").strip().lower() not in (
                "1",
                "true",
                "yes",
            )
            app.run(mouse=mouse)
        finally:
            restore_terminal_after_tui()
        if app._graceful_shutdown and not args.no_splash:
            print_shutdown_splash()
        write_exit_marker("graceful", log_path=session_log_path, exit_code=0)
        close_session_log()
    except StartupHardwareError as exc:
        for line in exc.lines:
            print(line)
        write_exit_marker("startup_error", log_path=session_log_path, detail=str(exc.lines[0] if exc.lines else ""))
        close_session_log()
        sys.exit(1)
    except HardwareInitializationError as e:
        logger.error(str(e))
        write_exit_marker("startup_error", log_path=session_log_path, detail=str(e))
        close_session_log()
        sys.exit(1)
    except ImportError as e:
        logger.error(f"No se pudo importar la TUI: {e}")
        logger.error("Configura el entorno: .\\setup\\install_drivers.ps1 → opción 3")
        write_exit_marker("python_error", log_path=session_log_path, detail=str(e))
        close_session_log()
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Saliendo...")
        restore_terminal_after_tui()
        if not args.no_splash:
            try:
                from tui.splash import print_shutdown_splash

                print_shutdown_splash()
            except Exception:
                pass
        write_exit_marker("keyboard_interrupt", log_path=session_log_path, exit_code=130)
        close_session_log()
        sys.exit(130)
    except Exception as e:
        restore_terminal_after_tui()
        import traceback

        traceback.print_exc(file=sys.stderr)
        logger.exception("Error fatal: %s", e)
        write_exit_marker("python_error", log_path=session_log_path, detail=str(e))
        close_session_log()
        sys.exit(1)


if __name__ == "__main__":
    main()
