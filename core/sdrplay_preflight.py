"""
xyz-sdr | core/sdrplay_preflight.py
Prueba RX SDRplay en subproceso aislado (segfault no tumba la TUI).
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Literal

from core.runtime_paths import project_root
from core.sdrplay_service import is_native_crash_exit_code

StreamPath = Literal["legacy", "minimal"]

DEFAULT_PREFLIGHT_TIMEOUT = 60.0
MIN_PER_PATH_TIMEOUT = 30.0

_DEVICE_KWARGS_BLOCK = """
    import os
    kwargs = {"driver": "sdrplay"}
    _serial = os.environ.get("XYZ_SDR_SDRPLAY_SERIAL", "").strip()
    if _serial:
        kwargs["serial"] = _serial
"""

_LEGACY_SCRIPT = f"""
import sys

def step(name: str) -> None:
    print(f"STEP:{{name}}", flush=True)

try:
    from core.soapy_runtime import bootstrap_soapy
    bootstrap_soapy(force=True)
    import numpy as np
    import SoapySDR
    from SoapySDR import SOAPY_SDR_CF32, SOAPY_SDR_RX

    step("bootstrap")
{_DEVICE_KWARGS_BLOCK}
    dev = SoapySDR.Device(kwargs)
    step("open")
    dev.setSampleRate(SOAPY_SDR_RX, 0, 500_000)
    step("setSampleRate")
    dev.setFrequency(SOAPY_SDR_RX, 0, 100.6e6)
    step("setFrequency")
    stream = dev.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
    step("setupStream")
    dev.activateStream(stream)
    step("activateStream")
    buff = np.empty(4096, np.complex64)
    sr = dev.readStream(stream, [buff], 4096, 1_000_000)
    step(f"readStream ret={{sr.ret}}")
    dev.deactivateStream(stream)
    dev.closeStream(stream)
    step("closeStream")
    if hasattr(dev, "close"):
        dev.close()
    step("device.close")
    print("OK", flush=True)
    sys.exit(0)
except Exception as exc:
    print(f"ERR {{exc}}", flush=True)
    sys.exit(2)
"""

_MINIMAL_SCRIPT = f"""
import sys

def step(name: str) -> None:
    print(f"STEP:{{name}}", flush=True)

try:
    from core.soapy_runtime import bootstrap_soapy
    bootstrap_soapy(force=True)
    import numpy as np
    import SoapySDR
    from SoapySDR import SOAPY_SDR_CF32, SOAPY_SDR_RX

    step("bootstrap")
{_DEVICE_KWARGS_BLOCK}
    dev = SoapySDR.Device(kwargs)
    step("open")
    stream = dev.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
    step("setupStream")
    dev.activateStream(stream)
    step("activateStream")
    buff = np.empty(4096, np.complex64)
    sr = dev.readStream(stream, [buff], 4096, 1_000_000)
    step(f"readStream ret={{sr.ret}}")
    dev.setSampleRate(SOAPY_SDR_RX, 0, 500_000)
    step("setSampleRate")
    dev.setFrequency(SOAPY_SDR_RX, 0, 100.6e6)
    step("setFrequency")
    dev.deactivateStream(stream)
    dev.closeStream(stream)
    step("closeStream")
    if hasattr(dev, "close"):
        dev.close()
    step("device.close")
    print("OK", flush=True)
    sys.exit(0)
except Exception as exc:
    print(f"ERR {{exc}}", flush=True)
    sys.exit(2)
"""

_STREAM_SCRIPTS: dict[StreamPath, str] = {
    "legacy": _LEGACY_SCRIPT,
    "minimal": _MINIMAL_SCRIPT,
}


@dataclass
class PreflightResult:
    ok: bool
    path: StreamPath | str
    segfault: bool
    last_step: str
    detail: str
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    skipped: bool = False
    skip_reason: str = ""


def is_device_unavailable_detail(detail: str) -> bool:
    lowered = (detail or "").lower()
    return (
        "no available rsp" in lowered
        or "no devices found" in lowered
        or "sdrplay_api_open()" in lowered
        or "servicenotresponding" in lowered.replace("_", "")
    )


def preflight_user_message(result: PreflightResult) -> str:
    """Mensaje UX según tipo de fallo (no tratar todo como segfault)."""
    if result.ok or result.skipped:
        return ""
    detail_l = (result.detail or "").lower()
    if result.segfault:
        return (
            "[ERR] SDRplay: el plugin/API crashea al configurar RX. "
            "Reinstala API: .\\setup\\install_sdrplay_api.bat "
            "(luego .\\setup\\install_soapy_sdrplay3.ps1 si hace falta). "
            "Diagnose: .\\scripts\\diagnose_sdrplay.ps1 --no-probe"
        )
    if is_device_unavailable_detail(result.detail):
        return (
            "[ERR] SDRplay: RSP no disponible para preflight "
            "(¿SDRuno u otra app usando el dispositivo?). "
            "Cierra otras apps SDR y ejecuta: Restart-Service SDRplayAPIService"
        )
    if result.last_step == "timeout" or "timeout" in detail_l:
        return (
            "[ERR] SDRplay: timeout al probar RX — SDRplayAPIService responde lento. "
            "Reinicia el servicio y reintenta."
        )
    return (
        "[ERR] SDRplay: preflight RX falló. "
        "Ejecuta .\\scripts\\diagnose_sdrplay.ps1"
    )


def skipped_preflight_result(reason: str) -> PreflightResult:
    return PreflightResult(
        ok=True,
        path="skipped",
        segfault=False,
        last_step="skipped",
        detail=reason,
        skipped=True,
        skip_reason=reason,
    )


def parse_stream_probe_output(
    stdout: str,
    returncode: int,
    *,
    path: StreamPath | str = "unknown",
) -> PreflightResult:
    """Interpreta salida del subproceso de prueba stream."""
    out = (stdout or "").strip()
    last_step = ""
    for line in out.splitlines():
        if line.startswith("STEP:"):
            last_step = line[5:].strip()

    segfault = is_native_crash_exit_code(returncode)
    if segfault:
        fail_step = last_step or "unknown"
        if fail_step == "open" and path == "legacy":
            fail_step = "setSampleRate"
        elif fail_step == "setupStream" and path == "legacy":
            fail_step = "activateStream"
        detail = out or f"native crash after STEP:{fail_step} (exit {returncode})"
        return PreflightResult(
            ok=False,
            path=path,
            segfault=True,
            last_step=fail_step,
            detail=detail,
        )

    if returncode == 0 and "OK" in out:
        return PreflightResult(
            ok=True,
            path=path,
            segfault=False,
            last_step=last_step or "done",
            detail=out,
        )

    return PreflightResult(
        ok=False,
        path=path,
        segfault=False,
        last_step=last_step,
        detail=out or f"exit code {returncode}",
    )


def _run_isolated_script(script: str, timeout: float) -> tuple[int, str, str, str]:
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            cwd=str(project_root()),
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        msg = "timeout (stream may be slow but did not crash)"
        return -1, "", msg, msg
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    combined = "\n".join(part for part in (stdout, stderr) if part).strip()
    return proc.returncode, stdout, stderr, combined


def resolve_preflight_timeout(explicit: float | None = None) -> float:
    """Timeout total (s) para preflight; env XYZ_SDR_PREFLIGHT_TIMEOUT."""
    if explicit is not None:
        return float(explicit)
    raw = os.environ.get("XYZ_SDR_PREFLIGHT_TIMEOUT", "").strip()
    if raw:
        try:
            return max(float(raw), MIN_PER_PATH_TIMEOUT * 2)
        except ValueError:
            pass
    return DEFAULT_PREFLIGHT_TIMEOUT


def per_path_timeout(total: float) -> float:
    return max(total / 2.0, MIN_PER_PATH_TIMEOUT)


def run_preflight(
    path: StreamPath = "minimal",
    timeout: float | None = None,
    *,
    per_path_timeout_s: float | None = None,
) -> PreflightResult:
    """Ejecuta una ruta de arranque RX en subproceso aislado."""
    if per_path_timeout_s is not None:
        effective = per_path_timeout_s
    elif timeout is not None:
        effective = per_path_timeout(float(timeout))
    else:
        effective = per_path_timeout(resolve_preflight_timeout())
    script = _STREAM_SCRIPTS.get(path, _MINIMAL_SCRIPT)
    returncode, stdout, stderr, combined = _run_isolated_script(script, effective)
    if returncode == -1:
        return PreflightResult(
            ok=False,
            path=path,
            segfault=False,
            last_step="timeout",
            detail=combined,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )
    result = parse_stream_probe_output(combined, returncode, path=path)
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def run_preflight_best(timeout: float | None = None) -> PreflightResult:
    """Prueba minimal y legacy; devuelve la primera ruta que funciona."""
    total = resolve_preflight_timeout(timeout)
    per = per_path_timeout(total)
    last = PreflightResult(
        ok=False,
        path="none",
        segfault=False,
        last_step="",
        detail="no stream path attempted",
    )
    for path in ("minimal", "legacy"):
        result = run_preflight(path, per_path_timeout_s=per)
        if result.ok:
            return result
        last = result
    return last


def preflight_status_label(result: PreflightResult | None) -> str:
    """Etiqueta corta para check_env: OK / FAIL / SEGFAULT."""
    if result is None:
        return "SKIP"
    if result.ok:
        return "OK"
    if result.segfault:
        return "SEGFAULT"
    return "FAIL"
