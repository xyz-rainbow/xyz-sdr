"""
xyz-sdr | core/device.py
Abstracción del hardware SDR usando SoapySDR.
Compatible con: SDRplay RSP1, RTL-SDR, HackRF, Airspy y cualquier dispositivo SoapySDR.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Optional

import numpy as np

from core.sdr_io import run_sdr_io
from core.soapy_runtime import bootstrap_soapy, get_soapy_module
from core.stream_stats import StreamStats

try:
    from core.session_log import log_breadcrumb
except ImportError:
    def log_breadcrumb(_msg: str, **kwargs) -> None:
        pass

logger = logging.getLogger(__name__)

_sdr_devices_open = 0

_soapy_mod: Any | None = None
SOAPY_SDR_RX: Any = None
SOAPY_SDR_CF32: Any = None
SOAPY_SDR_CS16: Any = None
SOAPY_SDR_OVERFLOW: int = -3


def _load_soapy() -> bool:
    """Carga SoapySDR bajo demanda tras bootstrap. Devuelve True si import OK."""
    global _soapy_mod, SOAPY_SDR_RX, SOAPY_SDR_CF32, SOAPY_SDR_CS16
    if _soapy_mod is not None:
        return True
    status = bootstrap_soapy()
    if not status.import_ok:
        return False
    try:
        mod = get_soapy_module()
        from SoapySDR import SOAPY_SDR_CF32 as _cf32, SOAPY_SDR_RX as _rx  # noqa: WPS433

        _soapy_mod = mod
        SOAPY_SDR_RX = _rx
        SOAPY_SDR_CF32 = _cf32
        try:
            from SoapySDR import SOAPY_SDR_CS16 as _cs16  # noqa: WPS433

            SOAPY_SDR_CS16 = _cs16
        except ImportError:
            SOAPY_SDR_CS16 = None
        try:
            from SoapySDR import SOAPY_SDR_OVERFLOW as _overflow  # noqa: WPS433

            SOAPY_SDR_OVERFLOW = int(_overflow)
        except ImportError:
            pass
        return True
    except ImportError:
        return False


def soapysdr_available() -> bool:
    """True si SoapySDR puede importarse tras bootstrap."""
    return _load_soapy()


class HardwareInitializationError(Exception):
    """Excepción lanzada cuando falla la inicialización del hardware real SDR."""
    pass


class SampleRateError(ValueError):
    """Sample rate / bandwidth no soportado por el dispositivo."""
    pass


BANDWIDTH_PRESETS: tuple[float, ...] = (
    250_000,
    500_000,
    1_000_000,
    2_048_000,
    4_000_000,
    8_000_000,
)

# Tasa IQ inicial al abrir hardware real (evita readStream agresivo antes del warmup).
SAFE_START_SAMPLE_RATE = 500_000.0
# MTU inicial conservador para plugins sdrplay (sube tras warmup en read_samples).
SDRPLAY_INITIAL_STREAM_MTU = 16_384
SDRPLAY_PROBE_READ_SAMPLES = 4_096


def _sdrplay_stream_mode() -> str:
    return os.environ.get("XYZ_SDR_SDRPLAY_STREAM_MODE", "minimal").strip().lower()


def _sdrplay_stream_format_name() -> str:
    return os.environ.get("XYZ_SDR_SDRPLAY_STREAM_FORMAT", "CF32").strip().upper()


def _sdrplay_uses_cs16() -> bool:
    return _sdrplay_stream_format_name() == "CS16" and SOAPY_SDR_CS16 is not None


def _sdrplay_soapy_stream_format() -> Any:
    if _sdrplay_uses_cs16():
        return SOAPY_SDR_CS16
    return SOAPY_SDR_CF32


def _format_bandwidth_hz(rate_hz: float) -> str:
    """DEPRECATED: usa core.formatting.format_bandwidth_hz()."""
    from core.formatting import format_bandwidth_hz
    return format_bandwidth_hz(rate_hz)


# Re-export para no romper imports existentes
from core.formatting import format_bandwidth_hz as _format_bandwidth_hz_public  # noqa: F401


def _rate_within_soapy_range(rate_hz: float, rate_range) -> bool:
    minimum = float(rate_range.minimum())
    maximum = float(rate_range.maximum())
    if rate_hz < minimum or rate_hz > maximum:
        return False
    step = float(rate_range.step())
    if step > 0:
        steps = round((rate_hz - minimum) / step)
        adjusted = minimum + steps * step
        if abs(adjusted - rate_hz) > max(step * 0.01, 1.0):
            return False
    return True


def _driver_name(kwargs: dict) -> str:
    return str(kwargs.get("driver", "")).lower()


_IGNORED_AUTO_DRIVERS = frozenset({"audio", "simulated"})
_PREFERRED_AUTO_ORDER = ("sdrplay", "rtlsdr", "hackrf", "airspy", "miri")
_MIRI_SDRPLAY_HINTS = ("sdrplay", "rsp", "mirics sdr")


def filter_sdr_devices(devices: list[dict]) -> list[dict]:
    """Excluye drivers de audio/simulación de la enumeración útil para RX."""
    return [dev for dev in devices if _driver_name(dev) not in _IGNORED_AUTO_DRIVERS]


def _device_label(dev: dict) -> str:
    return str(dev.get("label", "")).strip()


def _is_miri_sdrplay_proxy(dev: dict) -> bool:
    """True si el driver miri parece un proxy Mirics→SDRplay (no MSi2500/DVB genérico)."""
    if _driver_name(dev) != "miri":
        return False
    label = _device_label(dev).lower()
    if any(token in label for token in ("msi2500", "vtx3d", "dvb")):
        return False
    return any(hint in label for hint in _MIRI_SDRPLAY_HINTS)


def _summarize_devices(devices: list[dict]) -> str:
    counts: dict[str, int] = {}
    for dev in devices:
        name = _driver_name(dev) or "?"
        counts[name] = counts.get(name, 0) + 1
    return ", ".join(f"{name}×{count}" if count > 1 else name for name, count in counts.items())


def _device_option_label(dev: dict) -> str:
    drv = _driver_name(dev) or "?"
    label = _device_label(dev)
    return label if label else drv.upper()


def format_device_detail_lines(dev: dict | None, *, simulated: bool = False) -> list[str]:
    """Líneas compactas para la ficha del dispositivo en Ajustes → Hardware."""
    if simulated:
        return ["Modo simulación", "Sin hardware SDR real"]
    if not dev:
        return ["(ningún dispositivo seleccionado)"]
    drv = _driver_name(dev) or "?"
    label = _device_label(dev)
    serial = str(dev.get("serial", "")).strip()
    if label and serial:
        clean = label.replace(serial, "").strip() if serial in label else label
        lines = [clean, serial]
    elif label:
        lines = [label]
    else:
        lines = [drv.upper()]
    if serial and len(lines) == 1 and serial not in lines[0]:
        lines.append(serial)
    return lines


def resolve_settings_device_display(
    token: str | None,
    token_map: dict[str, str | dict],
    cached_devices: list[dict] | None,
    *,
    current_driver: str,
    simulated: bool,
) -> list[str]:
    """Resuelve la ficha visible bajo el Select de driver."""
    if simulated or str(current_driver).lower() in ("simulated", "sim"):
        return format_device_detail_lines(None, simulated=True)

    target = token_map.get(str(token or "")) if token else None
    if isinstance(target, dict):
        return format_device_detail_lines(target)

    driver_key = str(target or current_driver or "auto").lower()
    if driver_key in ("", "auto"):
        devices = filter_sdr_devices(cached_devices or [])
        if devices:
            return format_device_detail_lines(devices[0])
        return ["Auto — sin dispositivos en caché de arranque"]

    devices = filter_sdr_devices(cached_devices or [])
    for dev in devices:
        if _driver_name(dev) == driver_key:
            return format_device_detail_lines(dev)
    return [f"Preset: {driver_key.upper()}", "(no apareció en el último enumerate)"]


def _kwargs_match(left: dict | None, right: dict | None) -> bool:
    if not left or not right:
        return False
    keys = ("driver", "label", "serial", "device_id")
    for key in keys:
        if key in left or key in right:
            if str(left.get(key, "")) != str(right.get(key, "")):
                return False
    return _driver_name(left) == _driver_name(right)


def build_driver_select_options(
    devices: list[dict] | None = None,
    *,
    current_driver: str = "auto",
    active_kwargs: dict | None = None,
) -> tuple[list[tuple[str, str]], dict[str, str | dict], str]:
    """
    Opciones únicas para Select de driver (Esc → Ajustes).

    Devuelve (opciones, mapa token→driver|kwargs, token seleccionado).
    """
    if devices is None:
        devices = filter_sdr_devices(SDRDevice.list_devices())
    else:
        devices = filter_sdr_devices(devices)

    options: list[tuple[str, str]] = []
    token_map: dict[str, str | dict] = {}
    seen_presets: set[str] = set()

    presets = (
        ("Auto (primer dispositivo)", "auto"),
        ("SDRplay RSP", "sdrplay"),
        ("RTL-SDR Dongle", "rtlsdr"),
        ("HackRF One", "hackrf"),
        ("Airspy", "airspy"),
        ("Simulación (Hardware)", "simulated"),
    )
    for label, drv in presets:
        token = f"preset:{drv}"
        options.append((label, token))
        token_map[token] = drv
        seen_presets.add(drv)

    for index, dev in enumerate(devices):
        drv = _driver_name(dev)
        if not drv or drv in _IGNORED_AUTO_DRIVERS:
            continue
        token = f"dev:{index}"
        options.append((_device_option_label(dev), token))
        token_map[token] = dict(dev)

    driver_key = (current_driver or "auto").lower()
    if driver_key == "sim":
        driver_key = "simulated"

    selected = f"preset:{driver_key}" if driver_key in seen_presets else f"preset:auto"
    if active_kwargs:
        for token, target in token_map.items():
            if isinstance(target, dict) and _kwargs_match(target, active_kwargs):
                selected = token
                break
    elif driver_key not in seen_presets:
        for token, target in token_map.items():
            if isinstance(target, dict) and _driver_name(target) == driver_key:
                selected = token
                break

    if selected not in token_map:
        selected = "preset:auto"

    return options, token_map, selected


def _sdrplay_resolution_hint(devices: list[dict]) -> str:
    hints: list[str] = []
    if not any(_driver_name(dev) == "sdrplay" for dev in devices):
        hints.append(
            "Plugin SoapySDR 'sdrplay' sin dispositivos — ejecuta: SoapySDRUtil --find=driver=sdrplay"
        )
        try:
            from core.soapy_runtime import check_sdrplay_service_running

            if check_sdrplay_service_running():
                hints.append(
                    "SDRplayAPIService activo: cierra SDRuno y reinstala módulo Soapy sdrplay "
                    "(.\\setup\\install_drivers.ps1)."
                )
            else:
                hints.append("Inicia SDRplayAPIService (services.msc) y cierra SDRuno.")
        except Exception:
            pass
    for dev in devices:
        if _driver_name(dev) == "miri" and not _is_miri_sdrplay_proxy(dev):
            hints.append(
                f"Driver 'miri' detectado ({_device_label(dev)}) no es un SDRplay RSP — "
                "no se usará como sustituto de sdrplay."
            )
            break
    return " ".join(hints)


def resolve_device(driver: str, devices: list[dict] | None = None) -> dict:
    """Resuelve kwargs SoapySDR para abrir el dispositivo."""
    if devices is None:
        devices = filter_sdr_devices(SDRDevice.list_devices())
    else:
        devices = filter_sdr_devices(devices)

    if not devices:
        raise HardwareInitializationError("No hay dispositivos SDR enumerados por SoapySDR.")

    key = (driver or "auto").lower()
    if key in ("auto", ""):
        for preferred in _PREFERRED_AUTO_ORDER:
            for dev in devices:
                name = _driver_name(dev)
                if name == preferred:
                    if name == "miri" and not _is_miri_sdrplay_proxy(dev):
                        continue
                    return dict(dev)
        return dict(devices[0])

    if key == "simulated":
        return {"driver": "simulated"}

    if key == "sdrplay":
        for dev in devices:
            if _driver_name(dev) == "sdrplay":
                return dict(dev)
        for dev in devices:
            if _is_miri_sdrplay_proxy(dev):
                logger.info(
                    "Mapeando driver sdrplay solicitado al proxy miri: %s",
                    _device_label(dev),
                )
                return dict(dev)

        extra = _sdrplay_resolution_hint(devices)
        msg = (
            f"No se encontró dispositivo SDRplay RSP. "
            f"Enumerados: {_summarize_devices(devices)}."
        )
        if extra:
            msg = f"{msg} {extra}"
        raise HardwareInitializationError(msg)

    for dev in devices:
        name = _driver_name(dev)
        if name == key or key in name:
            return dict(dev)

    raise HardwareInitializationError(
        f"No se encontró dispositivo para driver={driver!r}. "
        f"Disponibles: {_summarize_devices(devices)}"
    )


class SimulatedSDR:
    """SDR simulado para desarrollo sin hardware conectado."""

    def __init__(self):
        self.center_freq = 100_600_000
        self.sample_rate = 2_048_000
        self.gain = 40.0
        self._t = 0.0

    def read_samples(self, num_samples: int) -> np.ndarray:
        t = np.linspace(self._t, self._t + num_samples / self.sample_rate, num_samples)
        self._t += num_samples / self.sample_rate

        noise = (np.random.randn(num_samples) + 1j * np.random.randn(num_samples)) * 0.02
        signal = noise.copy()

        simulated_stations = [
            (98_000_000, 0.5, "wbfm", 330.0),
            (100_600_000, 0.8, "wbfm", 440.0),
            (104_300_000, 0.4, "wbfm", 554.0),
            (105_400_000, 0.6, "wbfm", 659.0),
            (120_900_000, 0.3, "nbfm", 800.0),
            (446_006_250, 0.7, "nbfm", 1000.0),
            (4_855_000, 0.5, "lsb", 600.0),
        ]

        f_min = self.center_freq - self.sample_rate / 2
        f_max = self.center_freq + self.sample_rate / 2
        margin = 150_000.0

        for f_station, amplitude, mode, audio_freq in simulated_stations:
            if f_min - margin <= f_station <= f_max + margin:
                f_offset = f_station - self.center_freq
                if mode == "wbfm":
                    mod = np.sin(2 * np.pi * audio_freq * t) * 75_000.0
                    phase = 2 * np.pi * f_offset * t + (mod / (2 * np.pi * audio_freq))
                    station_sig = np.exp(1j * phase) * amplitude
                else:
                    mod = np.sin(2 * np.pi * audio_freq * t) * 3_000.0
                    phase = 2 * np.pi * f_offset * t + mod
                    station_sig = np.exp(1j * phase) * amplitude
                signal += station_sig

        return signal.astype(np.complex64)

    def close(self):
        pass


class SDRDevice:
    """Envuelve un dispositivo SoapySDR con una API sencilla."""

    def __init__(self, driver: str = "sdrplay", channel: int = 0):
        self.driver = driver
        self.channel = channel
        self._sdr = None
        self._stream = None
        self._lock = threading.Lock()
        self._device_kwargs: dict | None = None

        self.center_freq = 100_600_000.0
        self.sample_rate = 2_048_000.0
        self.gain = 40.0
        self.auto_gain = False
        self._stream_stats = StreamStats()
        self._sdrplay_pending_sample_rate: float | None = None
        self._sdrplay_stream_bootstrapped: bool = False

    def reset_stream_stats(self) -> None:
        with self._lock:
            self._stream_stats = StreamStats()

    @property
    def stream_stats(self) -> StreamStats:
        with self._lock:
            return self._stream_stats.copy()

    def _native_settings_deferred(self) -> bool:
        """
        SDRplay crashea si setSampleRate/setFrequency se llaman al abrir sin stream.
        Mantener estado en Python hasta start_stream (_prepare_stream_unlocked).
        """
        return (
            self.driver == "sdrplay"
            and self._stream is None
            and self._sdr is not None
            and not isinstance(self._sdr, SimulatedSDR)
        )

    def open(self, device_kwargs: dict | None = None) -> bool:
        if self.driver in ("simulated", "sim") and not device_kwargs:
            self.driver = "simulated"
            self._sdr = SimulatedSDR()
            return True

        if device_kwargs and str(device_kwargs.get("driver", "")).lower() in ("simulated", "sim"):
            self.driver = "simulated"
            self._device_kwargs = dict(device_kwargs)
            self._sdr = SimulatedSDR()
            return True

        return run_sdr_io(self._open_native, device_kwargs)

    def _open_native(self, device_kwargs: dict | None = None) -> bool:
        if not _load_soapy():
            raise HardwareInitializationError(
                "SoapySDR no disponible en el entorno Python. "
                "Ejecuta: python setup/check_env.py — o usa --sim."
            )

        try:
            if device_kwargs:
                kwargs = dict(device_kwargs)
            else:
                kwargs = resolve_device(self.driver)
            log_breadcrumb(f"device.open start driver={self.driver!r} kwargs={kwargs!r}")
            self._device_kwargs = kwargs
            resolved_driver = kwargs.get("driver", self.driver)
            with self._lock:
                self._sdr = _soapy_mod.Device(kwargs)
            self.driver = str(resolved_driver)
            if not isinstance(self._sdr, SimulatedSDR) and self.sample_rate > SAFE_START_SAMPLE_RATE:
                logger.info(
                    "Apertura conservadora: sample_rate %.0f Hz → %.0f Hz",
                    self.sample_rate,
                    SAFE_START_SAMPLE_RATE,
                )
                self.sample_rate = SAFE_START_SAMPLE_RATE
            if self._native_settings_deferred():
                log_breadcrumb(
                    "device.open sdrplay: defer native settings until start_stream"
                )
            else:
                self._apply_settings()
            global _sdr_devices_open
            _sdr_devices_open += 1
            logger.info("Dispositivo abierto: %s", kwargs)
            log_breadcrumb(
                f"device.open ok driver={self.driver!r} rate={self.sample_rate:.0f} "
                f"freq={self.center_freq:.0f} gain={self.gain:.1f}"
            )
            return True
        except HardwareInitializationError:
            raise
        except Exception as e:
            raise HardwareInitializationError(str(e)) from e

    def same_device_as(self, kwargs: dict | None) -> bool:
        return _kwargs_match(self._device_kwargs, kwargs)

    def close(self, *, fast: bool = False):
        if isinstance(self._sdr, SimulatedSDR) or self._sdr is None:
            self._close_impl(fast=fast)
            return
        if fast:
            self._close_impl(fast=True)
            return
        try:
            run_sdr_io(self._close_impl)
        except TimeoutError:
            logger.warning("device.close timeout; forcing fast cleanup")
            self._close_impl(fast=True)

    def _close_impl(self, *, fast: bool = False) -> None:
        log_breadcrumb("device.close start")
        global _sdr_devices_open
        if fast:
            acquired = self._lock.acquire(timeout=0.5)
            if not acquired:
                log_breadcrumb("device.close fast: lock busy, dropping handles")
                self._stream = None
                self._sdr = None
                return
        else:
            self._lock.acquire()
        try:
            if self._stream and soapysdr_available() and not isinstance(self._sdr, SimulatedSDR):
                try:
                    self._sdr.deactivateStream(self._stream)
                    self._sdr.closeStream(self._stream)
                except Exception as exc:
                    logger.warning("Error cerrando stream en close: %s", exc)
                self._stream = None
            if self._sdr:
                try:
                    self._sdr.close() if hasattr(self._sdr, "close") else None
                except Exception:
                    pass
                self._sdr = None
                if _sdr_devices_open > 0:
                    _sdr_devices_open -= 1
        finally:
            self._lock.release()
        logger.info("Dispositivo cerrado")

    def get_supported_sample_rates(self) -> list[float]:
        if self.is_simulated or self.driver == "simulated":
            return list(BANDWIDTH_PRESETS)

        if self._native_settings_deferred():
            return list(BANDWIDTH_PRESETS)

        if not self._sdr or not soapysdr_available():
            return list(BANDWIDTH_PRESETS)

        try:
            rate_range = self._sdr.getSampleRateRange(SOAPY_SDR_RX, self.channel)
            supported = [
                rate for rate in BANDWIDTH_PRESETS
                if _rate_within_soapy_range(rate, rate_range)
            ]
            if supported:
                return supported
        except Exception as exc:
            logger.warning("No se pudo consultar rango de sample rate: %s", exc)

        return list(BANDWIDTH_PRESETS)

    def is_sample_rate_supported(self, rate_hz: float) -> bool:
        supported = self.get_supported_sample_rates()
        return any(abs(rate_hz - candidate) < 1.0 for candidate in supported)

    def set_sample_rate(self, rate: float) -> None:
        if rate <= 0:
            raise SampleRateError(f"Sample rate inválido: {rate}")

        if not self.is_sample_rate_supported(rate):
            supported = ", ".join(_format_bandwidth_hz(r) for r in self.get_supported_sample_rates())
            raise SampleRateError(
                f"Bandwidth {_format_bandwidth_hz(rate)} no soportado. Opciones: {supported}"
            )

        if abs(self.sample_rate - rate) < 1.0:
            return

        if self._native_settings_deferred():
            if not any(abs(rate - candidate) < 1.0 for candidate in BANDWIDTH_PRESETS):
                supported = ", ".join(_format_bandwidth_hz(r) for r in BANDWIDTH_PRESETS)
                raise SampleRateError(
                    f"Bandwidth {_format_bandwidth_hz(rate)} no soportado. Opciones: {supported}"
                )
            self.sample_rate = rate
            logger.info(
                "sdrplay: bandwidth %s aplazado hasta iniciar RX",
                _format_bandwidth_hz(rate),
            )
            return

        if isinstance(self._sdr, SimulatedSDR) or self._sdr is None:
            self._set_sample_rate_impl(rate)
            return
        run_sdr_io(self._set_sample_rate_impl, rate)

    def _set_sample_rate_impl(self, rate: float) -> None:
        previous_rate = self.sample_rate
        self.sample_rate = rate

        try:
            if isinstance(self._sdr, SimulatedSDR):
                self._sdr.sample_rate = rate
            elif self._sdr and soapysdr_available():
                with self._lock:
                    self._apply_native_sample_rate_unlocked(rate)
        except Exception as exc:
            self.sample_rate = previous_rate
            raise SampleRateError(
                f"No se pudo aplicar bandwidth {_format_bandwidth_hz(rate)}: {exc}"
            ) from exc

        logger.info("Bandwidth: %s", _format_bandwidth_hz(rate))

    def _try_set_bandwidth_unlocked(self, rate_hz: float) -> None:
        if isinstance(self._sdr, SimulatedSDR) or not self._sdr or not soapysdr_available():
            return
        if not hasattr(self._sdr, "setBandwidth"):
            return
        try:
            self._sdr.setBandwidth(SOAPY_SDR_RX, self.channel, rate_hz)
        except Exception as exc:
            logger.debug("setBandwidth(%.0f Hz): %s", rate_hz, exc)

    def _clamp_gain_unlocked(self, gain_db: float) -> float:
        if isinstance(self._sdr, SimulatedSDR) or not self._sdr or not soapysdr_available():
            return gain_db
        try:
            gain_range = self._sdr.getGainRange(SOAPY_SDR_RX, self.channel)
            minimum = float(gain_range.minimum())
            maximum = float(gain_range.maximum())
            clamped = max(minimum, min(maximum, float(gain_db)))
            if abs(clamped - gain_db) > 0.01:
                logger.info(
                    "Ganancia ajustada %.1f → %.1f dB (rango %.1f–%.1f)",
                    gain_db,
                    clamped,
                    minimum,
                    maximum,
                )
            return clamped
        except Exception as exc:
            logger.debug("getGainRange: %s", exc)
            return gain_db

    def _apply_gain_unlocked(self) -> None:
        if isinstance(self._sdr, SimulatedSDR) or not self._sdr or not soapysdr_available():
            return
        self._sdr.setGainMode(SOAPY_SDR_RX, self.channel, self.auto_gain)
        if not self.auto_gain:
            self.gain = self._clamp_gain_unlocked(self.gain)
            self._sdr.setGain(SOAPY_SDR_RX, self.channel, self.gain)

    def _apply_settings(self):
        if not soapysdr_available() or isinstance(self._sdr, SimulatedSDR):
            if isinstance(self._sdr, SimulatedSDR):
                self._sdr.center_freq = self.center_freq
                self._sdr.sample_rate = self.sample_rate
                self._sdr.gain = self.gain
            return
        with self._lock:
            self._sdr.setSampleRate(SOAPY_SDR_RX, self.channel, self.sample_rate)
            self._try_set_bandwidth_unlocked(self.sample_rate)
            self._sdr.setFrequency(SOAPY_SDR_RX, self.channel, self.center_freq)
            self._apply_gain_unlocked()

    def _prepare_stream_unlocked(self, *, iq_rate_hz: float | None = None) -> None:
        """Re-sincroniza parámetros antes de activateStream (sdrplay es sensible)."""
        if isinstance(self._sdr, SimulatedSDR) or not self._sdr or not soapysdr_available():
            return
        rate = float(iq_rate_hz if iq_rate_hz is not None else self.sample_rate)
        self._sdr.setSampleRate(SOAPY_SDR_RX, self.channel, rate)
        self._try_set_bandwidth_unlocked(rate)
        self._sdr.setFrequency(SOAPY_SDR_RX, self.channel, self.center_freq)
        self._apply_gain_unlocked()

    def _apply_native_sample_rate_unlocked(self, rate: float) -> None:
        """Cambia sample rate nativo reiniciando stream si hace falta."""
        had_stream = self._stream is not None
        if had_stream:
            self._stop_stream()
            try:
                self._sdr.closeStream(self._stream)
            except Exception:
                pass
            self._stream = None
        if self.driver == "sdrplay":
            self._sdrplay_apply_tuning_unlocked(rate, mode="stopped")
        else:
            self._sdr.setSampleRate(SOAPY_SDR_RX, self.channel, rate)
            self._try_set_bandwidth_unlocked(rate)
            self._sdr.setFrequency(SOAPY_SDR_RX, self.channel, self.center_freq)
            self._apply_gain_unlocked()
        if had_stream:
            self._activate_stream(safe_sdrplay_start=False)

    def _sdrplay_apply_tuning_unlocked(self, rate: float, *, mode: str = "stopped") -> None:
        """Aplica freq/rate/gain en SDRplay con orden alternativo si falla."""
        if mode == "live" and self._stream is not None:
            try:
                self._sdr.setFrequency(SOAPY_SDR_RX, self.channel, self.center_freq)
                self._sdr.setSampleRate(SOAPY_SDR_RX, self.channel, rate)
                self._try_set_bandwidth_unlocked(rate)
                self._apply_gain_unlocked()
                log_breadcrumb("device.sdrplay.tuning live ok")
                return
            except Exception as exc:
                log_breadcrumb(f"device.sdrplay.tuning live FAIL: {exc}")

        last_exc: Exception | None = None
        for label, apply_fn in (
            ("stopped-freq-first", self._sdrplay_tune_stopped_freq_first),
            ("stopped-rate-first", self._sdrplay_tune_stopped_rate_first),
        ):
            try:
                apply_fn(rate)
                log_breadcrumb(f"device.sdrplay.tuning {label} ok")
                return
            except Exception as exc:
                last_exc = exc
                log_breadcrumb(f"device.sdrplay.tuning {label} FAIL: {exc}")
        if last_exc is not None:
            raise last_exc

    def _sdrplay_tune_stopped_freq_first(self, rate: float) -> None:
        self._sdr.setFrequency(SOAPY_SDR_RX, self.channel, self.center_freq)
        self._sdr.setSampleRate(SOAPY_SDR_RX, self.channel, rate)
        self._try_set_bandwidth_unlocked(rate)
        self._apply_gain_unlocked()

    def _sdrplay_tune_stopped_rate_first(self, rate: float) -> None:
        self._sdr.setSampleRate(SOAPY_SDR_RX, self.channel, rate)
        self._try_set_bandwidth_unlocked(rate)
        self._sdr.setFrequency(SOAPY_SDR_RX, self.channel, self.center_freq)
        self._apply_gain_unlocked()

    def _sdrplay_probe_read_unlocked(self) -> int:
        if _sdrplay_uses_cs16():
            buff = np.empty(SDRPLAY_PROBE_READ_SAMPLES * 2, dtype=np.int16)
        else:
            buff = np.empty(SDRPLAY_PROBE_READ_SAMPLES, dtype=np.complex64)
        sr = self._sdr.readStream(
            self._stream,
            [buff],
            SDRPLAY_PROBE_READ_SAMPLES,
            timeoutUs=int(1e6),
        )
        return int(getattr(sr, "ret", 0))

    def _activate_stream_sdrplay_legacy(self) -> None:
        """Activa stream SDRplay con tuning previo (ruta legacy)."""
        apply_rate = self.sample_rate
        if self.sample_rate > SAFE_START_SAMPLE_RATE:
            self._sdrplay_pending_sample_rate = self.sample_rate
            apply_rate = SAFE_START_SAMPLE_RATE
        else:
            self._sdrplay_pending_sample_rate = None

        log_breadcrumb(f"device.sdrplay.legacy_activate begin apply_rate={apply_rate:.0f}")
        
        # 1. Tuning previo (legacy)
        self._sdrplay_apply_tuning_unlocked(apply_rate, mode="stopped")
        
        # 2. Setup & Activate
        if self._stream is None:
            self._stream = self._sdr.setupStream(SOAPY_SDR_RX, _sdrplay_soapy_stream_format())
        self._try_set_stream_mtu_unlocked(SDRPLAY_INITIAL_STREAM_MTU)
        self._sdr.activateStream(self._stream)
        import time
        time.sleep(0.05)
        log_breadcrumb("device.sdrplay.legacy_activate activateStream ok")

        # 3. Probe read
        probe_ret = self._sdrplay_probe_read_unlocked()
        log_breadcrumb(f"device.sdrplay.probe_read ok ret={probe_ret}")
        
        self._sdrplay_stream_bootstrapped = True

    def _activate_stream_sdrplay_minimal(self) -> None:
        """Activa stream SDRplay sin setSampleRate previo (evita segfault en arranque)."""
        apply_rate = self.sample_rate
        if self.sample_rate > SAFE_START_SAMPLE_RATE:
            self._sdrplay_pending_sample_rate = self.sample_rate
            apply_rate = SAFE_START_SAMPLE_RATE
        else:
            self._sdrplay_pending_sample_rate = None

        log_breadcrumb(
            f"device.sdrplay.minimal_activate begin apply_rate={apply_rate:.0f} "
            f"target={self.sample_rate:.0f}"
        )
        if self._stream is None:
            self._stream = self._sdr.setupStream(SOAPY_SDR_RX, _sdrplay_soapy_stream_format())
        self._try_set_stream_mtu_unlocked(SDRPLAY_INITIAL_STREAM_MTU)
        self._sdr.activateStream(self._stream)
        time.sleep(0.05)
        log_breadcrumb("device.sdrplay.minimal_activate activateStream ok")

        probe_ret = self._sdrplay_probe_read_unlocked()
        log_breadcrumb(f"device.sdrplay.probe_read ok ret={probe_ret}")

        try:
            self._sdrplay_apply_tuning_unlocked(apply_rate, mode="live")
            self._sdrplay_stream_bootstrapped = True
            log_breadcrumb("device.sdrplay.minimal_activate stream ready (live tune)")
            return
        except Exception as exc:
            log_breadcrumb(f"device.sdrplay live tune failed: {exc}")

        self._stop_stream()
        try:
            self._sdr.closeStream(self._stream)
        except Exception:
            pass
        self._stream = None
        self._sdrplay_apply_tuning_unlocked(apply_rate, mode="stopped")
        self._stream = self._sdr.setupStream(SOAPY_SDR_RX, _sdrplay_soapy_stream_format())
        self._try_set_stream_mtu_unlocked(SDRPLAY_INITIAL_STREAM_MTU)
        self._sdr.activateStream(self._stream)
        time.sleep(0.05)
        self._sdrplay_stream_bootstrapped = True
        log_breadcrumb("device.sdrplay.minimal_activate stream ready (stopped tune)")

    def _try_set_stream_mtu_unlocked(self, mtu: int) -> None:
        if self._stream is None or not hasattr(self._sdr, "setStreamMTU"):
            return
        try:
            actual = int(self._sdr.setStreamMTU(self._stream, mtu))
            logger.info("Stream MTU: %d", actual)
        except Exception as exc:
            logger.debug("setStreamMTU(%d): %s", mtu, exc)

    def _stop_stream(self) -> None:
        if not self._stream or not soapysdr_available() or isinstance(self._sdr, SimulatedSDR):
            return
        try:
            self._sdr.deactivateStream(self._stream)
        except Exception as exc:
            logger.warning("Error desactivando stream RX: %s", exc)

    def _activate_stream(self, *, safe_sdrplay_start: bool = True) -> None:
        """Activa stream; el caller debe tener _lock si hace falta exclusión."""
        if isinstance(self._sdr, SimulatedSDR) or not self._sdr or not soapysdr_available():
            return

        if (
            self.driver == "sdrplay"
            and safe_sdrplay_start
            and not self._sdrplay_stream_bootstrapped
        ):
            mode = _sdrplay_stream_mode()
            if mode == "legacy":
                self._activate_stream_sdrplay_legacy()
            else:
                self._activate_stream_sdrplay_minimal()
            return

        iq_rate = self.sample_rate
        if (
            safe_sdrplay_start
            and self.driver == "sdrplay"
            and self.sample_rate > SAFE_START_SAMPLE_RATE
        ):
            self._sdrplay_pending_sample_rate = self.sample_rate
            iq_rate = SAFE_START_SAMPLE_RATE
            log_breadcrumb(
                f"sdrplay: stream start at {iq_rate:.0f} Hz, "
                f"target {self._sdrplay_pending_sample_rate:.0f} Hz after warmup"
            )
        self._prepare_stream_unlocked(iq_rate_hz=iq_rate)
        if self._stream is None:
            stream_fmt = (
                _sdrplay_soapy_stream_format()
                if self.driver == "sdrplay"
                else SOAPY_SDR_CF32
            )
            self._stream = self._sdr.setupStream(SOAPY_SDR_RX, stream_fmt)
        initial_mtu = SDRPLAY_INITIAL_STREAM_MTU if self.driver == "sdrplay" else 65_536
        self._try_set_stream_mtu_unlocked(initial_mtu)
        self._sdr.activateStream(self._stream)
        time.sleep(0.05)

    def maybe_ramp_sdrplay_sample_rate(self) -> bool:
        """
        Tras warmup RX, sube el sample rate nativo al objetivo (p. ej. 2 MHz FM).
        Evita crash al activar stream directamente a tasas altas en SDRplay.
        """
        pending = self._sdrplay_pending_sample_rate
        if pending is None or self.driver != "sdrplay":
            return False
        self._sdrplay_pending_sample_rate = None
        run_sdr_io(self._ramp_sdrplay_sample_rate_impl, pending)
        return True

    def _ramp_sdrplay_sample_rate_impl(self, target_hz: float) -> None:
        log_breadcrumb(f"sdrplay: ramp sample_rate to {target_hz:.0f}")
        with self._lock:
            self._apply_native_sample_rate_unlocked(target_hz)
        log_breadcrumb("sdrplay: ramp sample_rate ok")

    def stop_stream(self) -> None:
        """Detiene el stream RX (p. ej. al pulsar DETENER RX)."""
        if isinstance(self._sdr, SimulatedSDR) or self._sdr is None:
            self._stop_stream_impl()
            return
        run_sdr_io(self._stop_stream_impl)

    def _stop_stream_impl(self) -> None:
        with self._lock:
            self._stop_stream()

    def start_stream(self) -> None:
        """Activa el stream RX bajo demanda (no al abrir el dispositivo)."""
        if isinstance(self._sdr, SimulatedSDR) or not self._sdr or not soapysdr_available():
            return
        run_sdr_io(self._start_stream_impl)

    def _start_stream_impl(self) -> None:
        log_breadcrumb(
            f"device.start_stream rate={self.sample_rate:.0f} driver={self.driver!r}"
        )
        with self._lock:
            self._stream_stats = StreamStats()
            try:
                self._activate_stream()
            except Exception as exc:
                log_breadcrumb(f"device.start_stream FAIL: {exc}")
                try:
                    if self._stream:
                        self._sdr.closeStream(self._stream)
                except Exception:
                    pass
                self._stream = None
                raise RuntimeError(f"No se pudo activar stream RX: {exc}") from exc
        logger.info(
            "Stream RX activo | driver=%s kwargs=%s rate=%.0f Hz",
            self.driver,
            self._device_kwargs,
            self.sample_rate,
        )
        log_breadcrumb("device.start_stream ok")

    def _recover_stream_unlocked(self) -> None:
        """Reinicia stream; caller debe tener _lock."""
        if isinstance(self._sdr, SimulatedSDR) or not self._sdr or not soapysdr_available():
            return
        logger.warning("Reiniciando stream RX tras error Soapy")
        self._stream_stats.recoveries += 1
        if self._stream:
            try:
                self._sdr.deactivateStream(self._stream)
                self._sdr.closeStream(self._stream)
            except Exception:
                pass
            self._stream = None
        self._activate_stream(safe_sdrplay_start=False)

    @property
    def stream_active(self) -> bool:
        return self._stream is not None

    def set_frequency(self, freq_hz: float):
        self.center_freq = freq_hz
        if self._native_settings_deferred():
            return
        if self._sdr:
            if soapysdr_available() and not isinstance(self._sdr, SimulatedSDR):
                run_sdr_io(self._set_frequency_impl, freq_hz)
            elif isinstance(self._sdr, SimulatedSDR):
                self._sdr.center_freq = freq_hz

    def _set_frequency_impl(self, freq_hz: float) -> None:
        log_breadcrumb(f"device.set_frequency {freq_hz:.0f}")
        with self._lock:
            if isinstance(self._sdr, SimulatedSDR) or not self._sdr or not soapysdr_available():
                return
            had_stream = self._stream is not None
            if had_stream:
                self._stop_stream()
            self._sdr.setFrequency(SOAPY_SDR_RX, self.channel, freq_hz)
            if had_stream:
                try:
                    self._activate_stream(safe_sdrplay_start=False)
                except Exception as exc:
                    log_breadcrumb(f"device.set_frequency reactivate FAIL: {exc}")
                    raise RuntimeError(
                        f"No se pudo reactivar stream tras cambio de frecuencia: {exc}"
                    ) from exc
        log_breadcrumb("device.set_frequency ok")

    def set_gain(self, gain_db: float):
        self.gain = gain_db
        if self._native_settings_deferred():
            return
        if self._sdr and soapysdr_available() and not isinstance(self._sdr, SimulatedSDR):
            run_sdr_io(self._set_gain_impl, gain_db)

    def _set_gain_impl(self, gain_db: float) -> None:
        with self._lock:
            self._sdr.setGainMode(SOAPY_SDR_RX, self.channel, False)
            clamped = self._clamp_gain_unlocked(gain_db)
            self.gain = clamped
            self._sdr.setGain(SOAPY_SDR_RX, self.channel, clamped)

    def read_samples(self, num_samples: int = 256 * 1024) -> np.ndarray:
        if isinstance(self._sdr, SimulatedSDR):
            return self._read_samples_sim(num_samples)
        if not self._sdr or not soapysdr_available():
            return np.zeros(num_samples, dtype=np.complex64)
        return run_sdr_io(self._read_samples_impl, num_samples)

    def _read_samples_sim(self, num_samples: int) -> np.ndarray:
        with self._lock:
            self._stream_stats.read_calls += 1
            self._stream_stats.samples_requested += num_samples
        out = self._sdr.read_samples(num_samples)
        with self._lock:
            self._stream_stats.samples_received += len(out)
        return out

    def _read_samples_impl(self, num_samples: int) -> np.ndarray:
        if self._stream_stats.read_calls <= 1:
            log_breadcrumb(f"device.read_samples first n={num_samples}")
        if not self._stream:
            logger.warning("read_samples llamado sin stream RX activo")
            return np.zeros(num_samples, dtype=np.complex64)

        with self._lock:
            self._stream_stats.read_calls += 1
            self._stream_stats.samples_requested += num_samples

        buff = np.zeros(num_samples, dtype=np.complex64)
        read = 0
        chunk = min(num_samples, 65536)
        overflow_retries = 0
        use_cs16 = self.driver == "sdrplay" and _sdrplay_uses_cs16()

        if use_cs16:
            tmp_iq = np.empty(chunk * 2, dtype=np.int16)
        else:
            tmp = np.empty(chunk, dtype=np.complex64)

        while read < num_samples:
            to_read = min(chunk, num_samples - read)
            try:
                with self._lock:
                    if not self._stream:
                        break
                    if use_cs16:
                        tmp_view = tmp_iq[: to_read * 2]
                        sr = self._sdr.readStream(
                            self._stream, [tmp_view], to_read, timeoutUs=int(1e6)
                        )
                    else:
                        tmp_view = tmp[:to_read]
                        sr = self._sdr.readStream(
                            self._stream, [tmp_view], to_read, timeoutUs=int(1e6)
                        )
            except Exception as exc:
                logger.warning("readStream excepción: %s", exc)
                with self._lock:
                    self._stream_stats.read_errors += 1
                break
            if sr.ret > 0:
                if use_cs16:
                    raw = tmp_iq[: sr.ret * 2].astype(np.float32).reshape(-1, 2)
                    buff[read : read + sr.ret] = (raw[:, 0] + 1j * raw[:, 1]) / 32768.0
                else:
                    buff[read : read + sr.ret] = tmp_view[: sr.ret]
                read += sr.ret
                with self._lock:
                    self._stream_stats.samples_received += sr.ret
                continue
            if sr.ret == 0:
                with self._lock:
                    self._stream_stats.timeouts += 1
                logger.debug("readStream timeout sin muestras (%d/%d)", read, num_samples)
                break
            logger.warning("readStream error: %s", sr.ret)
            with self._lock:
                self._stream_stats.read_errors += 1
            if sr.ret == SOAPY_SDR_OVERFLOW and overflow_retries < 2:
                with self._lock:
                    self._stream_stats.overflows += 1
                overflow_retries += 1
                try:
                    with self._lock:
                        self._recover_stream_unlocked()
                except Exception as exc:
                    logger.warning("No se pudo recuperar stream: %s", exc)
                    break
                continue
            break

        return buff

    @staticmethod
    def list_devices(*, allow_while_open: bool = False) -> list[dict]:
        if _sdr_devices_open > 0 and not allow_while_open:
            logger.debug(
                "list_devices omitido: dispositivo Soapy abierto (evita crash/reentrada sdrplay)"
            )
            return []
        if not _load_soapy():
            return [{"driver": "simulated", "label": "Simulación (sin hardware)"}]
        return [dict(r) for r in _soapy_mod.Device.enumerate()]

    @property
    def is_simulated(self) -> bool:
        return isinstance(self._sdr, SimulatedSDR)

    def __repr__(self) -> str:
        status = "simulado" if self.is_simulated else "real"
        return f"SDRDevice(driver={self.driver!r}, freq={self.center_freq/1e6:.3f}MHz, {status})"
