"""xyz-sdr | core/sdrplay_wer.py — WER LocalDumps para capturar minidumps de python.exe.

Solo Windows. En Linux/macOS las funciones devuelven ``supported=False`` o
``(False, "...")`` según corresponda, sin tocar el registro.

Importante
==========

``winreg`` es stdlib **Windows-only**. El ``import winreg`` se hace dentro
de ``_require_winreg()`` (lazy) para que pytest pueda hacer collect de los
tests en runners Linux/macOS sin ``ModuleNotFoundError`` en tiempo de import.
El bug original era ``import winreg`` top-level — rompía toda la cadena
``core.sdrplay_wer → core.sdrplay_forensics → core.sdrplay_stream_matrix``
en CI Linux/macOS.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Tuple

from core.runtime_paths import project_root

_WER_EXECUTABLES = ("python.exe", "sdrplay_apiService.exe", "SoapySDRUtil.exe")


def _is_windows() -> bool:
    """Indica si el proceso corre en Windows.

    Helper aislado (no usar ``os.name`` directamente en condicionales) para
    que los tests puedan monkeypatchear el check sin tocar el módulo ``os``
    -- monkeypatchear ``os.name`` rompe pytest internals en runners Windows
    (Path(os.getcwd()) vs config.invocation_params.dir -> PosixPath crash).
    """
    return os.name == "nt"


def _require_winreg():
    """Devuelve el módulo ``winreg`` si estamos en Windows; raise si no.

    Lazy import para no romper el collect de pytest en Linux/macOS.
    Llamar después del guard ``os.name == "nt"`` para mensaje limpio.
    """
    if sys.platform != "win32" and os.name != "nt":
        raise RuntimeError("winreg no está disponible fuera de Windows")
    import winreg  # noqa: WPS433 — lazy por portabilidad

    return winreg


def _wer_hives() -> Tuple[Tuple[int, str], Tuple[int, str]]:
    """Pares (hive, label) — solo se evalúan dentro de Windows."""
    winreg = _require_winreg()
    return (
        (winreg.HKEY_CURRENT_USER, "HKCU"),
        (winreg.HKEY_LOCAL_MACHINE, "HKLM"),
    )


def _wer_key_for(exe_name: str) -> str:
    return rf"SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\{exe_name}"


def _read_wer_key(hive: int, exe_name: str = "python.exe") -> dict[str, str | int]:
    winreg = _require_winreg()
    data: dict[str, str | int] = {}
    key_path = _wer_key_for(exe_name)
    try:
        with winreg.OpenKey(hive, key_path) as key:
            for name, default in (("DumpFolder", ""), ("DumpType", 0), ("DumpCount", 0)):
                try:
                    val, _ = winreg.QueryValueEx(key, name)
                    data[name] = val
                except OSError:
                    data[name] = default
    except OSError:
        pass
    return data


def registry_dump_folder(*, dumps_dir: Path | None = None) -> Path:
    """Carpeta WER efectiva (HKCU gana sobre HKLM si existe)."""
    if not _is_windows():
        # No Windows: caer al default local (sin tocar registro).
        return (dumps_dir or default_dumps_dir()).resolve()
    for hive, _label in _wer_hives():
        cfg = _read_wer_key(hive, "python.exe")
        folder = str(cfg.get("DumpFolder") or "").strip()
        if folder:
            return Path(folder)
    return (dumps_dir or default_dumps_dir()).resolve()


def default_dumps_dir() -> Path:
    raw = os.environ.get("XYZ_SDR_WER_DUMP_FOLDER", "").strip()
    if raw:
        return Path(raw)
    return project_root() / "var" / "log" / "dumps"


def wer_status(*, dumps_dir: Path | None = None) -> dict[str, str | int | bool]:
    """Estado best-effort de LocalDumps para python.exe (solo Windows)."""
    folder = registry_dump_folder(dumps_dir=dumps_dir)
    status: dict[str, str | int | bool] = {
        "supported": _is_windows(),
        "configured": False,
        "configured_hkcu": False,
        "configured_hklm": False,
        "dump_folder": str(folder),
        "dump_type": 0,
        "dump_count": 0,
    }
    if not _is_windows():
        return status
    for hive, label in _wer_hives():
        cfg = _read_wer_key(hive, "python.exe")
        if cfg:
            status["configured"] = True
            status[f"configured_{label.lower()}"] = True
            if cfg.get("DumpType"):
                status["dump_type"] = int(cfg["DumpType"])
            if cfg.get("DumpFolder"):
                status["dump_folder"] = str(cfg["DumpFolder"])
    dump_path = Path(str(status["dump_folder"]))
    if dump_path.is_dir():
        status["dump_count"] = sum(1 for _ in dump_path.glob("python*.dmp"))
        if not status["dump_count"]:
            status["dump_count"] = sum(1 for _ in dump_path.rglob("*.dmp"))
    return status


def _apply_wer_registry(*, hive: int, folder: Path, dump_type: int, exe_name: str) -> None:
    winreg = _require_winreg()
    key_path = _wer_key_for(exe_name)
    with winreg.CreateKey(hive, key_path) as key:
        winreg.SetValueEx(key, "DumpFolder", 0, winreg.REG_EXPAND_SZ, str(folder))
        winreg.SetValueEx(key, "DumpType", 0, winreg.REG_DWORD, int(dump_type))
        winreg.SetValueEx(key, "DumpCount", 0, winreg.REG_DWORD, 10)


def enable_wer_minidumps(
    *,
    dumps_dir: Path | None = None,
    dump_type: int = 2,
) -> tuple[bool, str]:
    """
    Configura WER LocalDumps para python.exe.

    Intenta HKCU (sin admin) y luego HKLM. Devuelve (ok, mensaje).
    """
    if not _is_windows():
        return False, "WER LocalDumps solo aplica en Windows"

    winreg = _require_winreg()
    folder = (dumps_dir or default_dumps_dir()).resolve()
    folder.mkdir(parents=True, exist_ok=True)

    notes: list[str] = []
    ok_any = False

    for exe_name in _WER_EXECUTABLES:
        try:
            _apply_wer_registry(
                hive=winreg.HKEY_CURRENT_USER,
                folder=folder,
                dump_type=dump_type,
                exe_name=exe_name,
            )
            ok_any = True
            notes.append(f"HKCU/{exe_name} OK")
        except OSError as exc:
            notes.append(f"HKCU/{exe_name} skip: {exc}")

        try:
            _apply_wer_registry(
                hive=winreg.HKEY_LOCAL_MACHINE,
                folder=folder,
                dump_type=dump_type,
                exe_name=exe_name,
            )
            ok_any = True
            notes.append(f"HKLM/{exe_name} OK")
        except OSError as exc:
            notes.append(f"HKLM/{exe_name} skip: {exc}")

    if ok_any:
        summary = "; ".join(notes[:6])
        if len(notes) > 6:
            summary += f" … (+{len(notes) - 6})"
        return True, f"{summary} → {folder} (DumpType={dump_type})"

    ps_key = _wer_key_for("python.exe")
    ps = (
        f"$key='HKLM:\\{ps_key}'; "
        f"New-Item -Path $key -Force | Out-Null; "
        f"New-ItemProperty -Path $key -Name DumpFolder -PropertyType ExpandString "
        f"-Value '{folder}' -Force | Out-Null; "
        f"New-ItemProperty -Path $key -Name DumpType -PropertyType DWord "
        f"-Value {int(dump_type)} -Force | Out-Null; "
        "New-ItemProperty -Path $key -Name DumpCount -PropertyType DWord -Value 10 -Force | Out-Null"
    )
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except OSError as ps_exc:
        return False, f"WER setup failed: {ps_exc}"
    if res.returncode != 0:
        detail = (res.stderr or res.stdout or "").strip()
        if "Access is denied" in detail or "Acceso denegado" in detail:
            return (
                False,
                "WER requiere admin para HKLM o ejecutar como usuario normal (HKCU). "
                f"Ejecuta: .\\scripts\\enable_wer_minidumps.ps1",
            )
        return False, detail or f"WER setup exit {res.returncode}"
    return True, f"HKLM OK (elevated) → {folder} (DumpType={dump_type})"