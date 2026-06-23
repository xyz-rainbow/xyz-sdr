"""
xyz-sdr | main.py
Punto de entrada principal. Lanza la TUI o el modo CLI.
"""

from __future__ import annotations

import sys
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
    parser.add_argument("--driver",   default=None, help="Driver SDR (sdrplay, rtlsdr, hackrf...)")
    parser.add_argument("--freq",     type=float, default=None, help="Frecuencia inicial en MHz")
    parser.add_argument("--gain",     type=float, default=None, help="Ganancia en dB")
    parser.add_argument("--mode",     default=None, choices=["wbfm","nbfm","am","usb","lsb"], help="Modo de demodulación")
    parser.add_argument("--sim",      action="store_true", help="Forzar modo simulación (sin hardware)")
    parser.add_argument("--check",    action="store_true", help="Verificar entorno y salir")
    parser.add_argument("--list-dev", action="store_true", help="Listar dispositivos y salir")
    parser.add_argument("--config",   default="config/defaults.toml", help="Ruta al archivo de configuración")
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


def print_banner_and_loader():
    """Muestra un banner ASCII en el centro y una barra de carga animada."""
    import os
    import time
    try:
        term_size = os.get_terminal_size()
        width = term_size.columns
        height = term_size.lines
    except OSError:
        width = 80
        height = 24

    # ANSI terminal colors
    C_RED = "\033[91m"
    C_ORANGE = "\033[38;5;208m"
    C_LIME = "\033[92m"
    C_CYAN = "\033[96m"
    C_PURPLE = "\033[95m"
    C_PINK = "\033[38;5;205m"
    C_RESET = "\033[0m"

    banner_lines = [
        "██████╗  ██╗  ██╗ ██╗   ██╗ ███████╗            ███████╗ ██████╗  ██████╗  ██████╗",
        "██╔═══╝  ╚██╗██╔╝ ╚██╗ ██╔╝ ╚══███╔╝ █████████╗ ██╔════╝ ██╔══██╗ ██╔══██╗ ╚═══██║",
        "██║       ╚███╔╝   ╚████╔╝     ███╔╝ ╚════════╝ ███████╗ ██║  ██║ ██████╔╝     ██║",
        "██║       ██╔██╗    ╚██╔╝     ███╔╝  █████████╗ ╚════██║ ██║  ██║ ██╔══██╗     ██║",
        "██████╗  ██╔╝ ██╗    ██║     ███████╗            ███████║ ██████╔╝ ██║  ██║ ██████║",
        "╚═════╝  ╚═╝  ╚═╝    ╚═╝     ╚══════╝            ╚══════╝ ╚═════╝  ╚═╝  ╚═╝ ╚═════╝",
        "─────────────────────────────────────────────────────────────────────────────────────────"
    ]

    colors = [C_RED, C_ORANGE, C_LIME, C_CYAN, C_PURPLE, C_PINK, C_CYAN]

    # Limpiar pantalla
    os.system('cls' if os.name == 'nt' else 'clear')

    # Centrado vertical
    v_padding = max(0, (height - len(banner_lines) - 4) // 2)
    print("\n" * v_padding, end="")

    # Imprimir banner centrado horizontalmente
    for line, color in zip(banner_lines, colors):
        pad = max(0, (width - len(line)) // 2)
        print(" " * pad + color + line + C_RESET)

    print()

    # Barra de carga animada
    bar_width = 40
    # Centrado horizontal de la barra
    bar_pad = max(0, (width - bar_width - 8) // 2)
    
    steps = 20
    for i in range(steps + 1):
        percent = int((i / steps) * 100)
        filled = int((i / steps) * bar_width)
        empty = bar_width - filled
        
        bar_color = "\033[96m" if percent < 50 else "\033[92m"
        bar = "█" * filled + "░" * empty
        
        sys.stdout.write(f"\r" + " " * bar_pad + f"{C_RESET}[{bar_color}{bar}{C_RESET}] {percent:3d}%")
        sys.stdout.flush()
        time.sleep(0.06)  # ~1.2 segundos de carga total

    print()
    time.sleep(0.2)


def main():
    args   = parse_args()
    config = load_config(args.config)

    # ── Modo check ──────────────────────────────────────────────────────────
    if args.check:
        import subprocess
        result = subprocess.run([sys.executable, "setup/check_env.py"])
        sys.exit(result.returncode)

    # ── Listar dispositivos ─────────────────────────────────────────────────
    if args.list_dev:
        from core.device import SDRDevice
        devices = SDRDevice.list_devices()
        if not devices:
            print("No se encontraron dispositivos SDR.")
        else:
            print(f"Dispositivos encontrados: {len(devices)}")
            for i, d in enumerate(devices):
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
        from core.device import SOAPYSDR_AVAILABLE
        has_hardware = False
        if SOAPYSDR_AVAILABLE:
            try:
                import SoapySDR
                devices = SoapySDR.Device.enumerate()
                if devices:
                    has_hardware = True
            except Exception:
                pass
        
        if not has_hardware:
            if sys.stdin.isatty():
                print("⚠️  No se detectó hardware SDR ni controladores de SoapySDR.")
                try:
                    response = input("¿Deseas iniciar en modo Simulado (Simulación sin Hardware)? [S/n]: ").strip().lower()
                except (KeyboardInterrupt, EOFError):
                    print("\nOperación cancelada.")
                    sys.exit(0)
                
                if response in ("", "s", "si", "y", "yes"):
                    print("🛰️  Iniciando en modo Simulado...")
                    driver = "simulated"
                else:
                    print("Cancelando ejecución. Conecte un dispositivo SDR e instale los drivers necesarios.")
                    sys.exit(0)
            else:
                print("⚠️  No se detectó hardware SDR ni controladores de SoapySDR. Fallback automático a modo Simulado (no interactivo).")
                driver = "simulated"

    logger.info(f"Iniciando xyz-sdr | driver={driver} freq={center_freq/1e6:.3f}MHz mode={demod_mode}")

    # ── Lanzar TUI ─────────────────────────────────────────────────────────
    try:
        from tui.app import XyzSDRApp
        from core.device import HardwareInitializationError
        app = XyzSDRApp(
            driver=driver,
            center_freq=center_freq,
            gain=gain,
            volume=volume,
            demod_mode=demod_mode,
            config=config,
        )
        print_banner_and_loader()
        app.run()
    except HardwareInitializationError as e:
        logger.error(str(e))
        sys.exit(1)
    except ImportError as e:
        logger.error(f"No se pudo importar la TUI: {e}")
        logger.error("Instala las dependencias: pip install -r requirements.txt")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Saliendo...")
    except Exception as e:
        logger.exception(f"Error fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
