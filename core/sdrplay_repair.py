"""
xyz-sdr | core/sdrplay_repair.py
Rutas de reparación SDRplay (API + plugin) para diagnose/preflight.
"""

from __future__ import annotations

from setup.bundled_installers import (
    bundled_sdrplay_installer_path,
    local_sdrplay_installer_candidates,
)


def sdrplay_api_installer_hint() -> str:
    """Indica de dónde puede instalarse la API v3.15."""
    bundled = bundled_sdrplay_installer_path(verify_manifest=False)
    if bundled is not None:
        return f"bundle embebido: {bundled}"
    local = local_sdrplay_installer_candidates()
    if local:
        return f"instalador local: {local[0]}"
    return (
        "descarga automática vía .\\setup\\install_sdrplay_api.bat "
        "(o coloca SDRplay_RSP_API-Windows-3.15.exe en Downloads / "
        "resources/installers/win-x64/)"
    )


def sdrplay_api_repair_recommendations(*, include_plugin: bool = True) -> list[str]:
    """
    Pasos recomendados cuando stream test / RX crashea (segfault nativo).

    El plugin Soapy solo no repara crashes en setupStream si la API está rota.
    """
    hint = sdrplay_api_installer_hint()
    recs = [
        f"1) Cierra SDRuno y xyz-sdr. Reinstala SDRplay API: .\\setup\\install_sdrplay_api.bat ({hint})",
        "2) O menú completo: .\\setup\\install_drivers.ps1 → [1] Instalar o reparar todo",
        "3) Tras instalar: Restart-Service SDRplayAPIService; Start-Sleep 10; prueba SDRuno con el RSP1",
        "4) Diagnose: .\\scripts\\diagnose_sdrplay.ps1 --no-probe",
    ]
    if include_plugin:
        recs.append(
            "5) Plugin Soapy (solo si API + SDRuno OK): .\\setup\\install_soapy_sdrplay3.ps1"
        )
    return recs


def volk_warning_is_benign(stderr_or_stdout: str) -> bool:
    """True si el único aviso relevante es SoapyVOLK (no causa segfault)."""
    text = (stderr_or_stdout or "").lower()
    return "soapyvolkconverters" in text or "volk config file" in text
