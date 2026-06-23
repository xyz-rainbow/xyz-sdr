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
import subprocess
from pathlib import Path

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

# ─── 2. SoapySDR ────────────────────────────────────────────────────────────

step("SoapySDR")
try:
    import SoapySDR
    ok(f"SoapySDR importado correctamente")

    # Buscar dispositivos
    results = SoapySDR.Device.enumerate()
    if results:
        ok(f"Dispositivos encontrados: {len(results)}")
        for r in results:
            print(f"    → driver={r.get('driver','?')} label={r.get('label','?')}")
    else:
        warn("Ningún dispositivo SDR detectado (¿está conectado?)")
except ImportError:
    fail("SoapySDR no instalado. Instala PothosSDR y añádelo al PATH.")
    errors.append("soapysdr")
except Exception as e:
    warn(f"SoapySDR importado pero error al enumerar dispositivos: {e}")

# ─── 3. SoapySDR utility en PATH ────────────────────────────────────────────

step("SoapySDRUtil (CLI)")
try:
    result = subprocess.run(
        ["SoapySDRUtil", "--find"],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode == 0:
        ok("SoapySDRUtil disponible en PATH")
    else:
        warn("SoapySDRUtil encontrado pero sin dispositivos.")
except FileNotFoundError:
    fail("SoapySDRUtil no encontrado en PATH.")
    warn("Añade 'C:\\Program Files\\PothosSDR\\bin' al PATH del sistema.")
    errors.append("soapysdrutil")
except Exception as e:
    warn(f"Error ejecutando SoapySDRUtil: {e}")

# ─── 4. Librerías Python core ───────────────────────────────────────────────

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
        
        # Realizar chequeo adicional de dispositivos de salida de audio para sounddevice
        if pkg == "sounddevice":
            try:
                import sounddevice as sd
                devices = sd.query_devices()
                outputs = [d for d in devices if d.get('max_output_channels', 0) > 0]
                if outputs:
                    ok(f"  → Audio: {len(outputs)} dispositivos de salida detectados")
                    default_dev = sd.default.device[1]
                    if default_dev is not None and default_dev >= 0 and default_dev < len(devices):
                        print(f"    → Salida por defecto: {devices[default_dev].get('name')}")
                    else:
                        print(f"    → Salida por defecto: ID {default_dev}")
                else:
                    warn("  → Audio: No se detectaron dispositivos de salida de audio activos.")
            except Exception as ae:
                warn(f"  → Audio: Error al consultar dispositivos: {ae}")
    except ImportError:
        fail(f"{label} — no instalado (pip install {pkg})")
        errors.append(pkg)

# Verificar parser TOML
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

# ─── 5. Librerías IA (opcionales) ───────────────────────────────────────────

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

print("\n" + "="*50)
if not errors:
    print("\033[92m  [OK] Todo listo. Ejecuta: python main.py\033[0m")
else:
    print(f"\033[91m  [FAIL] {len(errors)} problema(s) encontrado(s):\033[0m")
    for e in errors:
        print(f"    - {e}")
    print("\n  Ejecuta: .\\setup\\install_drivers.ps1")
print("="*50 + "\n")

sys.exit(0 if not errors else 1)
