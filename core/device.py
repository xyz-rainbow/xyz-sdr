"""
xyz-sdr | core/device.py
Abstracción del hardware SDR usando SoapySDR.
Compatible con: SDRplay RSP1, RTL-SDR, HackRF, Airspy y cualquier dispositivo SoapySDR.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

import numpy as np

from core.soapy_runtime import bootstrap_soapy, get_soapy_module
from core.stream_stats import StreamStats

logger = logging.getLogger(__name__)

_soapy_mod: Any | None = None
SOAPY_SDR_RX: Any = None
SOAPY_SDR_CF32: Any = None
SOAPY_SDR_OVERFLOW: int = -3


def _load_soapy() -> bool:
    """Carga SoapySDR bajo demanda tras bootstrap. Devuelve True si import OK."""
    global _soapy_mod, SOAPY_SDR_RX, SOAPY_SDR_CF32
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


def _format_bandwidth_hz(rate_hz: float) -> str:
    if rate_hz >= 1_000_000:
        value = rate_hz / 1_000_000
        text = f"{value:.3f}".rstrip("0").rstrip(".")
        return f"{text} MHz"
    if rate_hz >= 1_000:
        return f"{rate_hz / 1_000:.0f} kHz"
    return f"{rate_hz:.0f} Hz"


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


def resolve_device(driver: str, devices: list[dict] | None = None) -> dict:
    """Resuelve kwargs SoapySDR para abrir el dispositivo."""
    if devices is None:
        devices = SDRDevice.list_devices()
        devices = [d for d in devices if d.get("driver") != "simulated"]

    if not devices:
        raise HardwareInitializationError("No hay dispositivos SDR enumerados por SoapySDR.")

    key = (driver or "auto").lower()
    if key in ("auto", ""):
        return dict(devices[0])

    if key == "simulated":
        return {"driver": "simulated"}

    for dev in devices:
        name = _driver_name(dev)
        if name == key or key in name:
            return dict(dev)

    raise HardwareInitializationError(
        f"No se encontró dispositivo para driver={driver!r}. "
        f"Disponibles: {[d.get('driver') for d in devices]}"
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

    def reset_stream_stats(self) -> None:
        with self._lock:
            self._stream_stats = StreamStats()

    @property
    def stream_stats(self) -> StreamStats:
        with self._lock:
            return self._stream_stats.copy()

    def open(self) -> bool:
        if self.driver in ("simulated", "sim"):
            self.driver = "simulated"
            self._sdr = SimulatedSDR()
            return True

        if not _load_soapy():
            raise HardwareInitializationError(
                "SoapySDR no disponible en el entorno Python. "
                "Ejecuta: python setup/check_env.py — o usa --sim."
            )

        try:
            kwargs = resolve_device(self.driver)
            self._device_kwargs = kwargs
            resolved_driver = kwargs.get("driver", self.driver)
            self._sdr = _soapy_mod.Device(kwargs)
            self.driver = str(resolved_driver)
            self._apply_settings()
            logger.info("Dispositivo abierto: %s", kwargs)
            return True
        except HardwareInitializationError:
            raise
        except Exception as e:
            raise HardwareInitializationError(str(e)) from e

    def close(self):
        with self._lock:
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
        logger.info("Dispositivo cerrado")

    def get_supported_sample_rates(self) -> list[float]:
        if self.is_simulated or self.driver == "simulated":
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

        previous_rate = self.sample_rate
        self.sample_rate = rate

        try:
            if isinstance(self._sdr, SimulatedSDR):
                self._sdr.sample_rate = rate
            elif self._sdr and soapysdr_available():
                with self._lock:
                    had_stream = self._stream is not None
                    if had_stream:
                        self._stop_stream()
                        try:
                            self._sdr.closeStream(self._stream)
                        except Exception:
                            pass
                        self._stream = None
                    self._sdr.setSampleRate(SOAPY_SDR_RX, self.channel, rate)
                    self._sdr.setFrequency(SOAPY_SDR_RX, self.channel, self.center_freq)
                    self._sdr.setGainMode(SOAPY_SDR_RX, self.channel, self.auto_gain)
                    if not self.auto_gain:
                        self._sdr.setGain(SOAPY_SDR_RX, self.channel, self.gain)
                    if had_stream:
                        try:
                            self._activate_stream()
                        except Exception as exc:
                            raise SampleRateError(
                                f"No se pudo reactivar stream tras cambio de bandwidth: {exc}"
                            ) from exc
        except Exception as exc:
            self.sample_rate = previous_rate
            raise SampleRateError(
                f"No se pudo aplicar bandwidth {_format_bandwidth_hz(rate)}: {exc}"
            ) from exc

        logger.info("Bandwidth: %s", _format_bandwidth_hz(rate))

    def _apply_settings(self):
        if not soapysdr_available() or isinstance(self._sdr, SimulatedSDR):
            if isinstance(self._sdr, SimulatedSDR):
                self._sdr.center_freq = self.center_freq
                self._sdr.sample_rate = self.sample_rate
                self._sdr.gain = self.gain
            return
        self._sdr.setSampleRate(SOAPY_SDR_RX, self.channel, self.sample_rate)
        self._sdr.setFrequency(SOAPY_SDR_RX, self.channel, self.center_freq)
        self._sdr.setGainMode(SOAPY_SDR_RX, self.channel, self.auto_gain)
        if not self.auto_gain:
            self._sdr.setGain(SOAPY_SDR_RX, self.channel, self.gain)

    def _stop_stream(self) -> None:
        if not self._stream or not soapysdr_available() or isinstance(self._sdr, SimulatedSDR):
            return
        try:
            self._sdr.deactivateStream(self._stream)
        except Exception as exc:
            logger.warning("Error desactivando stream RX: %s", exc)

    def _activate_stream(self) -> None:
        """Activa stream; el caller debe tener _lock si hace falta exclusión."""
        if isinstance(self._sdr, SimulatedSDR) or not self._sdr or not soapysdr_available():
            return
        if self._stream is None:
            self._stream = self._sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        self._sdr.activateStream(self._stream)

    def stop_stream(self) -> None:
        """Detiene el stream RX (p. ej. al pulsar DETENER RX)."""
        with self._lock:
            self._stop_stream()

    def start_stream(self) -> None:
        """Activa el stream RX bajo demanda (no al abrir el dispositivo)."""
        if isinstance(self._sdr, SimulatedSDR) or not self._sdr or not soapysdr_available():
            return
        with self._lock:
            self._stream_stats = StreamStats()
            try:
                self._activate_stream()
            except Exception as exc:
                try:
                    if self._stream:
                        self._sdr.closeStream(self._stream)
                except Exception:
                    pass
                self._stream = None
                raise RuntimeError(f"No se pudo activar stream RX: {exc}") from exc

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
        self._activate_stream()

    @property
    def stream_active(self) -> bool:
        return self._stream is not None

    def set_frequency(self, freq_hz: float):
        self.center_freq = freq_hz
        if self._sdr:
            if soapysdr_available() and not isinstance(self._sdr, SimulatedSDR):
                self._sdr.setFrequency(SOAPY_SDR_RX, self.channel, freq_hz)
            elif isinstance(self._sdr, SimulatedSDR):
                self._sdr.center_freq = freq_hz

    def set_gain(self, gain_db: float):
        self.gain = gain_db
        if self._sdr and soapysdr_available() and not isinstance(self._sdr, SimulatedSDR):
            self._sdr.setGainMode(SOAPY_SDR_RX, self.channel, False)
            self._sdr.setGain(SOAPY_SDR_RX, self.channel, gain_db)

    def read_samples(self, num_samples: int = 256 * 1024) -> np.ndarray:
        if isinstance(self._sdr, SimulatedSDR):
            with self._lock:
                self._stream_stats.read_calls += 1
                self._stream_stats.samples_requested += num_samples
            out = self._sdr.read_samples(num_samples)
            with self._lock:
                self._stream_stats.samples_received += len(out)
            return out

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

        # Pre-asignar buffer temporal para reutilizar y evitar allocations en bucle
        tmp = np.empty(chunk, dtype=np.complex64)

        while read < num_samples:
            to_read = min(chunk, num_samples - read)
            tmp_view = tmp[:to_read]
            with self._lock:
                sr = self._sdr.readStream(self._stream, [tmp_view], to_read, timeoutUs=int(1e6))
            if sr.ret > 0:
                buff[read:read + sr.ret] = tmp_view[:sr.ret]
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
    def list_devices() -> list[dict]:
        if not _load_soapy():
            return [{"driver": "simulated", "label": "Simulación (sin hardware)"}]
        return [dict(r) for r in _soapy_mod.Device.enumerate()]

    @property
    def is_simulated(self) -> bool:
        return isinstance(self._sdr, SimulatedSDR)

    def __repr__(self) -> str:
        status = "simulado" if self.is_simulated else "real"
        return f"SDRDevice(driver={self.driver!r}, freq={self.center_freq/1e6:.3f}MHz, {status})"
