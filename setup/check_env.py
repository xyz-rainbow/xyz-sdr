#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
"""
xyz-sdr | check_env.py
Verifica que todos los componentes necesarios estén instalados correctamente.
"""

import sys
import struct
import subprocess
from pathlib import Path

# Bootstrap Soapy antes de cualquier import del paquete
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.soapy_runtime import (  # noqa: E402
    bootstrap_soapy,
    check_sdrplay_api,
    check_sdrplay_plugin,
    find_pothos_install,
    format_hardware_help,
    is_python_64bit,
)

# ─── Helpers ────────────────────────────────────────────────────────────────

def ok(msg):    print(f"  \033[92m[OK]\033[0m {msg}")
def warn(msg):  print(f"  \033[93m[!!]\033[0m {msg}")
def fail(msg):  print(f"  \033[91m[XX]\033[0m {msg}")
def step(msg):  print(f"\n\033[96m[>>] {msg}\033[0m")

errors = []

# ─── 1. Python version ───────────────────────────────────────────────────────

step("Python")
v = sys.version_info
if v.major == 3 and v.minor >= 10:
    ok(f"Python {v.major}.{v.minor}.{v.micro}")
else:
    fail(f"Python 3.10+ requerido. Tienes: {v.major}.{v.minor}.{v.micro}")
    errors.append("python_version")

if is_python_64bit():
    ok("Arquitectura: 64-bit (amd64)")
else:
    fail("Se requiere Python 64-bit para PothosSDR/SoapySDR.")
    errors.append("python_bitness")

from core.soapy_runtime import _soapy_pip_supported  # noqa: E402

if v.major == 3 and v.minor >= 13:
    warn(
        f"Python {v.major}.{v.minor}: no hay wheel SoapySDR en pip. "
        "Para hardware real usa Python 3.11 o 3.12."
    )
elif not _soapy_pip_supported():
    warn(f"Python {v.major}.{v.minor} puede no tener soporte SoapySDR en pip.")
else:
    ok("Versión compatible con pip SoapySDR o bindings Pothos 3.9")

# ─── 2. PothosSDR / rutas ───────────────────────────────────────────────────

step("PothosSDR")
pothos = find_pothos_install()
if pothos:
    ok(f"Instalación detectada: {pothos}")
    bin_dir = os.path.join(pothos, "bin")
    if os.path.isdir(bin_dir):
        ok(f"bin: {bin_dir}")
else:
    fail("PothosSDR no encontrado. Ejecuta setup\\install_drivers.bat → [2].")
    errors.append("pothos")

# ─── 3. SDRplay API ───────────────────────────────────────────────────────────

step("SDRplay API v3")
if check_sdrplay_api():
    ok("SDRplay API detectada (carpeta, DLL o servicio)")
else:
    fail("SDRplay API no detectada. Instala opción [1] en install_drivers.")
    errors.append("sdrplay_api")

# ─── 4. SoapySDR (Python + dispositivos) ─────────────────────────────────────

step("SoapySDR (Python)")
status = bootstrap_soapy(force=True)

if status.import_ok:
    ok("SoapySDR importado correctamente")
    if status.pothos_bin:
        ok(f"DLL path: {status.pothos_bin}")
            if status.python_bindings_path:
                ver = f"python{sys.version_info.major}.{sys.version_info.minor}"
                expected = os.path.join(status.pothos_root or "", "lib", ver, "site-packages")
                if os.path.normcase(status.python_bindings_path) == os.path.normcase(expected):
                    ok(f"Bindings: {status.python_bindings_path}")
                else:
                    warn(
                        f"Bindings embebidos son para otra versión: {status.python_bindings_path}"
                    )
                    warn(f"Con Python {sys.version_info.major}.{sys.version_info.minor}: pip install SoapySDR")
    if status.devices:
        ok(f"Dispositivos encontrados: {len(status.devices)}")
        for r in status.devices:
            print(f"    → driver={r.get('driver', '?')} label={r.get('label', '?')}")
    else:
        warn("Ningún dispositivo SDR detectado (¿está conectado? ¿SDRuno cerrado?)")
else:
    fail("SoapySDR no importa en Python.")
    help_text = format_hardware_help(status)
    for line in help_text.splitlines():
        print(f"    {line}")
    errors.append("soapysdr")

# ─── 5. Plugin sdrplay ───────────────────────────────────────────────────────

step("SoapySDR plugin sdrplay")
if check_sdrplay_plugin():
    ok("SoapySDRUtil --find=driver=sdrplay OK")
else:
    warn("Plugin sdrplay no visible vía SoapySDRUtil.")
    warn("Comprueba PATH (PothosSDR\\bin) y reinicia la terminal.")

# ─── 6. SoapySDRUtil en PATH ─────────────────────────────────────────────────

step("SoapySDRUtil (CLI)")
try:
    result = subprocess.run(
        ["SoapySDRUtil", "--find"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode == 0:
        ok("SoapySDRUtil disponible en PATH")
    else:
        warn("SoapySDRUtil encontrado pero sin dispositivos.")
except FileNotFoundError:
    fail("SoapySDRUtil no encontrado en PATH.")
    warn("Añade 'C:\\Program Files\\PothosSDR\\bin' al PATH del usuario y reinicia la terminal.")
    errors.append("soapysdrutil")
except Exception as e:
    warn(f"Error ejecutando SoapySDRUtil: {e}")

# ─── 7. Librerías Python core ───────────────────────────────────────────────

step("Librerías Python")

packages = {
    "numpy":        "NumPy (DSP)",
    "scipy":        "SciPy (filtros)",
    "sounddevice":  "sounddevice (audio output)",
    "textual":      "Textual (TUI)",
    "rich":         "Rich (terminal styling)",
}

for pkg, label in packages.items():
    try:
        __import__(pkg)
        ok(label)

        if pkg == "sounddevice":
            try:
                import sounddevice as sd
                devices = sd.query_devices()
                outputs = [d for d in devices if d.get("max_output_channels", 0) > 0]
                if outputs:
                    ok(f"  → Audio: {len(outputs)} dispositivos de salida detectados")
                else:
                    warn("  → Audio: No se detectaron dispositivos de salida de audio activos.")
            except Exception as ae:
                warn(f"  → Audio: Error al consultar dispositivos: {ae}")
    except ImportError:
        fail(f"{label} — no instalado (pip install {pkg})")
        errors.append(pkg)

try:
    if sys.version_info >= (3, 11):
        import tomllib
        ok("tomllib (TOML parser integrado)")
    else:
        import tomli
        ok("tomli (TOML parser)")
except ImportError:
    fail("tomli — no instalado (requerido para Python < 3.11, pip install tomli)")
    errors.append("tomli")

# ─── 8. Módulos IA (opcionales) ─────────────────────────────────────────────

step("Módulos IA (opcionales)")

ai_packages = {
    "faster_whisper": "faster-whisper (transcripción de voz)",
    "sklearn":        "scikit-learn (clasificación de señales)",
}

for pkg, label in ai_packages.items():
    try:
        __import__(pkg)
        ok(label)
    except ImportError:
        warn(f"{label} — no instalado (opcional, pip install {pkg.replace('_','-')})")

# ─── Resumen ────────────────────────────────────────────────────────────────

print("\n" + "=" * 50)
if not errors:
    print("\033[92m  [OK] Todo listo. Ejecuta: python main.py --list-dev\033[0m")
else:
    print(f"\033[91m  [FAIL] {len(errors)} problema(s) encontrado(s):\033[0m")
    for e in errors:
        print(f"    - {e}")
    print("\n  Ejecuta: .\\setup\\install_drivers.bat")
    print("  Tras instalar PATH, cierra y reabre la terminal.")
print("=" * 50 + "\n")

sys.exit(0 if not errors else 1)
