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
StreamFormat = Literal["CF32", "CS16"]

DEFAULT_PREFLIGHT_TIMEOUT = 60.0
MIN_PER_PATH_TIMEOUT = 30.0

_PREFLIGHT_TRY_ORDER: tuple[tuple[StreamPath, StreamFormat], ...] = (
    ("minimal", "CS16"),
    ("minimal", "CF32"),
    ("legacy", "CS16"),
    ("legacy", "CF32"),
)

_DEVICE_KWARGS_BLOCK = """
    import os
    kwargs = {"driver": "sdrplay"}
    _serial = os.environ.get("XYZ_SDR_SDRPLAY_SERIAL", "").strip()
    if _serial:
        kwargs["serial"] = _serial
"""

def _soapy_imports(stream_format: StreamFormat) -> str:
    if stream_format == "CS16":
        return "from SoapySDR import SOAPY_SDR_CS16, SOAPY_SDR_RX"
    return "from SoapySDR import SOAPY_SDR_CF32, SOAPY_SDR_RX"


def _soapy_fmt_symbol(stream_format: StreamFormat) -> str:
    return "SOAPY_SDR_CS16" if stream_format == "CS16" else "SOAPY_SDR_CF32"


def _read_buffer_block(stream_format: StreamFormat) -> str:
    if stream_format == "CS16":
        return "    buff = np.empty(8192, np.int16)"
    return "    buff = np.empty(4096, np.complex64)"


def build_preflight_script(
    path: StreamPath,
    *,
    stream_format: StreamFormat = "CF32",
    sample_rate: int | None = None,
) -> str:
    fmt = stream_format.upper()
    if fmt not in ("CF32", "CS16"):
        fmt = "CF32"
    soapy_imports = _soapy_imports(fmt)  # type: ignore[arg-type]
    fmt_sym = _soapy_fmt_symbol(fmt)  # type: ignore[arg-type]
    buff_block = _read_buffer_block(fmt)  # type: ignore[arg-type]

    if path == "legacy":
        rate_block = ""
        if sample_rate is not None:
            rate_block = f"""
    dev.setSampleRate(SOAPY_SDR_RX, 0, {sample_rate})
    step("setSampleRate")
"""
        return f"""
import sys

def step(name: str) -> None:
    print(f"STEP:{{name}}", flush=True)

try:
    from core.soapy_runtime import bootstrap_soapy
    bootstrap_soapy(force=True)
    import numpy as np
    import SoapySDR
    {soapy_imports}

    step("bootstrap")
{_DEVICE_KWARGS_BLOCK}
    dev = SoapySDR.Device(kwargs)
    step("open")
{rate_block}
    dev.setFrequency(SOAPY_SDR_RX, 0, 100.6e6)
    step("setFrequency")
    stream = dev.setupStream(SOAPY_SDR_RX, {fmt_sym})
    step("setupStream")
    dev.activateStream(stream)
    step("activateStream")
{buff_block}
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

    tune_after = ""
    if sample_rate is not None:
        tune_after = f"""
    dev.setSampleRate(SOAPY_SDR_RX, 0, {sample_rate})
    step("setSampleRate")
    dev.setFrequency(SOAPY_SDR_RX, 0, 100.6e6)
    step("setFrequency")
"""
    else:
        tune_after = """
    dev.setSampleRate(SOAPY_SDR_RX, 0, 500_000)
    step("setSampleRate")
    dev.setFrequency(SOAPY_SDR_RX, 0, 100.6e6)
    step("setFrequency")
"""
    return f"""
import sys

def step(name: str) -> None:
    print(f"STEP:{{name}}", flush=True)

try:
    from core.soapy_runtime import bootstrap_soapy
    bootstrap_soapy(force=True)
    import numpy as np
    import SoapySDR
    {soapy_imports}

    step("bootstrap")
{_DEVICE_KWARGS_BLOCK}
    dev = SoapySDR.Device(kwargs)
    step("open")
    stream = dev.setupStream(SOAPY_SDR_RX, {fmt_sym})
    step("setupStream")
    dev.activateStream(stream)
    step("activateStream")
{buff_block}
    sr = dev.readStream(stream, [buff], 4096, 1_000_000)
    step(f"readStream ret={{sr.ret}}")
{tune_after}
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
    stream_format: StreamFormat | str = "CF32"
    sample_rate: int | None = None


def apply_preflight_strategy(result: PreflightResult) -> None:
    """Publica la ruta ganadora para device.py / matriz."""
    if not result.ok:
        return
    os.environ["XYZ_SDR_SDRPLAY_STREAM_MODE"] = str(result.path)
    os.environ["XYZ_SDR_SDRPLAY_STREAM_FORMAT"] = str(result.stream_format or "CF32").upper()
    if result.sample_rate is not None:
        os.environ["XYZ_SDR_SDRPLAY_STREAM_SAMPLE_RATE"] = str(int(result.sample_rate))


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
    stream_format: StreamFormat | str = "CF32",
    sample_rate: int | None = None,
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
            stream_format=stream_format,
            sample_rate=sample_rate,
        )

    if returncode == 0 and "OK" in out:
        return PreflightResult(
            ok=True,
            path=path,
            segfault=False,
            last_step=last_step or "done",
            detail=out,
            stream_format=stream_format,
            sample_rate=sample_rate,
        )

    return PreflightResult(
        ok=False,
        path=path,
        segfault=False,
        last_step=last_step,
        detail=out or f"exit code {returncode}",
        stream_format=stream_format,
        sample_rate=sample_rate,
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
    stream_format: StreamFormat | str = "CF32",
    sample_rate: int | None = None,
) -> PreflightResult:
    """Ejecuta una ruta de arranque RX en subproceso aislado."""
    if per_path_timeout_s is not None:
        effective = per_path_timeout_s
    elif timeout is not None:
        effective = per_path_timeout(float(timeout))
    else:
        effective = per_path_timeout(resolve_preflight_timeout())

    fmt = str(stream_format).upper()
    if fmt not in ("CF32", "CS16"):
        fmt = "CF32"

    script = build_preflight_script(path, stream_format=fmt, sample_rate=sample_rate)  # type: ignore[arg-type]
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
            stream_format=fmt,
            sample_rate=sample_rate,
        )
    result = parse_stream_probe_output(
        combined,
        returncode,
        path=path,
        stream_format=fmt,
        sample_rate=sample_rate,
    )
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def run_preflight_best(
    timeout: float | None = None,
    *,
    try_order: tuple[tuple[StreamPath, StreamFormat], ...] | None = None,
) -> PreflightResult:
    """Prueba rutas/formatos; devuelve la primera que funciona (CS16 primero)."""
    total = resolve_preflight_timeout(timeout)
    per = per_path_timeout(total)
    order = try_order or _PREFLIGHT_TRY_ORDER
    last = PreflightResult(
        ok=False,
        path="none",
        segfault=False,
        last_step="",
        detail="no stream path attempted",
    )
    for path, fmt in order:
        result = run_preflight(path, per_path_timeout_s=per, stream_format=fmt)
        if result.ok:
            apply_preflight_strategy(result)
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
