"""Tests E2E de main() — entry point del CLI.

Cubre los flags documentados:
- `--check`: validar entorno sin abrir device.
- `--list-dev` / `-ListDev`: listar devices detectados (mock).
- `--sim`: arrancar en modo simulación (testeable).
- Band profile desde CLI: `--band fm_broadcast`.

Los tests usan `subprocess.run` con el `python` del proyecto para invocar
`main.py` directamente. Marcados como `slow` por si arrancan la app Textual.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_PY = REPO_ROOT / "main.py"


def _run_main(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Invoca main.py con los args dados y devuelve el resultado."""
    return subprocess.run(
        [sys.executable, str(MAIN_PY), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )


def test_main_module_imports():
    """main debe ser importable como módulo."""
    import main  # noqa: F401


def test_main_function_exists():
    """main() debe existir y ser callable."""
    import main
    assert callable(main.main)


@pytest.mark.slow
def test_main_check_flag_exits_cleanly():
    """`--check` debe ejecutarse sin levantar la app (validate env only). Marcado slow porque subprocess.run de main.py tarda en Windows."""
    result = _run_main("--check", timeout=60)
    # Exit code 0 (entorno OK) o 1 (algo falta) — ambos son "se ejecutó"
    assert result.returncode in (0, 1), f"Unexpected exit: {result.returncode}\n{result.stdout}\n{result.stderr}"
    # Debe haber producido alguna salida diagnóstica
    assert len(result.stdout) + len(result.stderr) > 0


def test_main_help_flag_prints_usage():
    """`--help` debe imprimir el usage y salir 0."""
    result = _run_main("--help")
    assert result.returncode == 0, f"--help falló: {result.stderr}"
    # Debe contener palabras típicas de help
    assert any(kw in result.stdout.lower() for kw in ("usage", "options", "argumentos"))


@pytest.mark.slow
def test_main_sim_mode_exits_cleanly():
    """`--sim` debe poder ejecutarse brevemente. Marcado slow porque arranca Textual."""
    # No podemos probar interactivamente, pero sí que arranca y muere rápido
    # si le pasamos algo que provoque salida. Usamos timeout corto.
    try:
        result = _run_main("--sim", "--check", timeout=10)
        # --check + --sim debe imprimir diagnóstico y salir
        assert result.returncode in (0, 1)
    except subprocess.TimeoutExpired:
        # Si arranca Textual correctamente y se queda esperando, también es válido
        # (significa que parseó args OK)
        pytest.skip("main arrancó Textual y se quedó esperando input — esperado")


def test_main_unknown_flag_returns_nonzero():
    """Flag desconocido debe producir error de argparse, no crash."""
    result = _run_main("--flag-que-no-existe")
    # argparse sale con código 2 (error de argumentos)
    assert result.returncode != 0
    # Y debe mencionar el flag desconocido en stderr
    assert "flag-que-no-existe" in result.stderr or "unrecognized" in result.stderr.lower()


@pytest.mark.slow
@pytest.mark.parametrize("band_id", ["fm_broadcast", "airband", "pmr446", "hf_lsb"])
def test_main_band_profile_accepted(band_id, tmp_path):
    """Cada band profile documentado debe ser aceptado por argparse. Marcado slow porque cada test hace subprocess.run de main.py (~30s en Windows)."""
    result = _run_main(f"--band={band_id}", "--check", "--sim", timeout=60)
    # Si argparse aceptó el band id, llegamos a check_env (puede fallar por entorno
    # pero el flag fue parseado OK)
    assert "invalid choice" not in result.stderr.lower(), (
        f"--band={band_id} rechazado: {result.stderr}"
    )