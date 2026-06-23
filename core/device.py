"""
xyz-sdr | core/device.py
Abstracción del hardware SDR usando SoapySDR.
Compatible con: SDRplay RSP1, RTL-SDR, HackRF, Airspy y cualquier dispositivo SoapySDR.
"""

from __future__ import annotations

import logging
import threading
import numpy as np
from typing import Optional

try:
    import SoapySDR
    from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32
    SOAPYSDR_AVAILABLE = True
except ImportError:
    SOAPYSDR_AVAILABLE = False
    logging.warning("SoapySDR no disponible — usando modo simulación")

class HardwareInitializationError(Exception):
    """Excepción lanzada cuando falla la inicialización del hardware real SDR."""
    pass


class SampleRateError(ValueError):
    """Sample rate / bandwidth no soportado por el dispositivo."""
    pass


# Presets de bandwidth IQ (Hz) — se filtran según capacidades del hardware
BANDWIDTH_PRESETS: tuple[float, ...] = (
    250_000,
    500_000,
    1_000_000,
    2_048_000,
    4_000_000,
    8_000_000,
)

logger = logging.getLogger(__name__)


def _format_bandwidth_hz(rate_hz: float) -> str:
    """Etiqueta legible para logs y UI."""
    if rate_hz >= 1_000_000:
        value = rate_hz / 1_000_000
        text = f"{value:.3f}".rstrip("0").rstrip(".")
        return f"{text} MHz"
    if rate_hz >= 1_000:
        return f"{rate_hz / 1_000:.0f} kHz"
    return f"{rate_hz:.0f} Hz"


def _rate_within_soapy_range(rate_hz: float, rate_range) -> bool:
    """Comprueba si un rate cae dentro del rango reportado por SoapySDR."""
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


# ─── Modo simulación (sin hardware) ─────────────────────────────────────────

class SimulatedSDR:
    """SDR simulado para desarrollo sin hardware conectado."""

    def __init__(self):
        self.center_freq   = 100_600_000
        self.sample_rate   = 2_048_000
        self.gain          = 40.0
        self._running      = False
        self._t            = 0.0

    def read_samples(self, num_samples: int) -> np.ndarray:
        """Genera señales de radio simuladas realistas basadas en frecuencias absolutas fijas."""
        t = np.linspace(self._t, self._t + num_samples / self.sample_rate, num_samples)
        self._t += num_samples / self.sample_rate

        # Ruido de fondo gaussian (ruido térmico del receptor)
        noise = (np.random.randn(num_samples) + 1j * np.random.randn(num_samples)) * 0.02
        signal = noise.copy()

        # Estaciones simuladas absolutas (frecuencia Hz, amplitud, tipo, frecuencia audio Hz)
        simulated_stations = [
            (98_000_000, 0.5, "wbfm", 330.0),    # 40 Principales (98.0 MHz) - Tono 330 Hz (E4)
            (100_600_000, 0.8, "wbfm", 440.0),   # RNE Radio Nacional (100.6 MHz) - Tono 440 Hz (A4)
            (104_300_000, 0.4, "wbfm", 554.0),   # Radio 3 (104.3 MHz) - Tono 554 Hz (C#5)
            (105_400_000, 0.6, "wbfm", 659.0),   # Cadena SER (105.4 MHz) - Tono 659 Hz (E5)
            (120_900_000, 0.3, "nbfm", 800.0),   # Aviación (120.9 MHz) - Pitido 800 Hz
            (446_006_250, 0.7, "nbfm", 1000.0),  # PMR Canal 1 (446.00625 MHz) - Pitido 1000 Hz
            (4_855_000, 0.5, "lsb", 600.0),      # Tiempo HF (4.855 MHz) - Zumbido 600 Hz
        ]

        # Límites del espectro actualmente capturado
        f_min = self.center_freq - self.sample_rate / 2
        f_max = self.center_freq + self.sample_rate / 2
        margin = 150_000.0  # Margen para transiciones suaves al salir del viewport

        for f_station, amplitude, mode, audio_freq in simulated_stations:
            if f_min - margin <= f_station <= f_max + margin:
                f_offset = f_station - self.center_freq
                
                # Simular modulación en frecuencia con tono audible
                if mode == "wbfm":
                    # Desviación de frecuencia ancha (~75 kHz)
                    mod = np.sin(2 * np.pi * audio_freq * t) * 75_000.0
                    phase = 2 * np.pi * f_offset * t + (mod / (2 * np.pi * audio_freq))
                    station_sig = np.exp(1j * phase) * amplitude
                else:
                    # Desviación de frecuencia estrecha (~3 kHz)
                    mod = np.sin(2 * np.pi * audio_freq * t) * 3_000.0
                    phase = 2 * np.pi * f_offset * t + mod
                    station_sig = np.exp(1j * phase) * amplitude

                signal += station_sig

        return signal.astype(np.complex64)

    def close(self):
        pass


# ─── Dispositivo real (SoapySDR) ────────────────────────────────────────────

class SDRDevice:
    """
    Envuelve un dispositivo SoapySDR con una API sencilla.

    Uso:
        dev = SDRDevice(driver="sdrplay")
        dev.open()
        dev.set_frequency(100.6e6)
        samples = dev.read_samples(1024 * 256)
        dev.close()
    """

    def __init__(self, driver: str = "sdrplay", channel: int = 0):
        self.driver   = driver
        self.channel  = channel
        self._sdr     = None
        self._stream  = None
        self._lock    = threading.Lock()

        # Parámetros actuales
        self.center_freq  = 100_600_000.0
        self.sample_rate  = 2_048_000.0
        self.gain         = 40.0
        self.auto_gain    = False

    # ── Apertura / cierre ───────────────────────────────────────────────────

    def open(self) -> bool:
        """Abre el dispositivo SDR. Retorna True si éxito.
        Lanza HardwareInitializationError si falla la inicialización real.
        """
        if self.driver == "simulated":
            self._sdr = SimulatedSDR()
            return True

        if not SOAPYSDR_AVAILABLE:
            raise HardwareInitializationError(
                "SoapySDR no disponible en el entorno Python. "
                "Por favor, instala SoapySDR o usa el modo simulado (--sim)."
            )

        try:
            self._sdr = SoapySDR.Device(dict(driver=self.driver))
            self._apply_settings()
            self._start_stream()
            logger.info(f"Dispositivo abierto: driver={self.driver}")
            return True
        except Exception as e:
            raise HardwareInitializationError(str(e))

    def close(self):
        """Cierra el stream y el dispositivo."""
        with self._lock:
            self._stop_stream()
            if self._sdr:
                try:
                    self._sdr.close() if hasattr(self._sdr, "close") else None
                except Exception:
                    pass
                self._sdr = None
        logger.info("Dispositivo cerrado")

    # ── Bandwidth / sample rate ─────────────────────────────────────────────

    def get_supported_sample_rates(self) -> list[float]:
        """Lista de bandwidths disponibles para el dispositivo abierto."""
        if self.is_simulated or self.driver == "simulated":
            return list(BANDWIDTH_PRESETS)

        if not self._sdr or not SOAPYSDR_AVAILABLE:
            return list(BANDWIDTH_PRESETS)

        try:
            rate_range = self._sdr.getSampleRateRange(SOAPY_SDR_RX, self.channel)
            supported = [
                rate for rate in BANDWIDTH_PRESETS
                if _rate_within_soapy_range(rate, rate_range)
            ]
            if supported:
                return supported
            logger.warning(
                "Ningún preset encaja en el rango Soapy [%s, %s]; usando presets por defecto",
                rate_range.minimum(),
                rate_range.maximum(),
            )
        except Exception as exc:
            logger.warning("No se pudo consultar rango de sample rate: %s", exc)

        return list(BANDWIDTH_PRESETS)

    def is_sample_rate_supported(self, rate_hz: float) -> bool:
        """Indica si el dispositivo admite el bandwidth solicitado."""
        supported = self.get_supported_sample_rates()
        return any(abs(rate_hz - candidate) < 1.0 for candidate in supported)

    def set_sample_rate(self, rate: float) -> None:
        """Establece la tasa de muestreo (bandwidth IQ) en Hz."""
        if rate <= 0:
            raise SampleRateError(f"Sample rate inválido: {rate}")

        if not self.is_sample_rate_supported(rate):
            supported = ", ".join(_format_bandwidth_hz(r) for r in self.get_supported_sample_rates())
            raise SampleRateError(
                f"Bandwidth {_format_bandwidth_hz(rate)} no soportado. "
                f"Opciones: {supported}"
            )

        if abs(self.sample_rate - rate) < 1.0:
            return

        previous_rate = self.sample_rate
        self.sample_rate = rate

        try:
            if isinstance(self._sdr, SimulatedSDR):
                self._sdr.sample_rate = rate
            elif self._sdr and SOAPYSDR_AVAILABLE:
                with self._lock:
                    had_stream = self._stream is not None
                    if had_stream:
                        self._stop_stream()
                    self._sdr.setSampleRate(SOAPY_SDR_RX, self.channel, rate)
                    # Reafirmar frecuencia y ganancia tras cambio de rate
                    self._sdr.setFrequency(SOAPY_SDR_RX, self.channel, self.center_freq)
                    self._sdr.setGainMode(SOAPY_SDR_RX, self.channel, self.auto_gain)
                    if not self.auto_gain:
                        self._sdr.setGain(SOAPY_SDR_RX, self.channel, self.gain)
                    if had_stream:
                        self._start_stream()
        except Exception as exc:
            self.sample_rate = previous_rate
            raise SampleRateError(f"No se pudo aplicar bandwidth {_format_bandwidth_hz(rate)}: {exc}") from exc

        logger.info("Bandwidth: %s", _format_bandwidth_hz(rate))

    # ── Configuración ───────────────────────────────────────────────────────

    def _apply_settings(self):
        """Aplica la configuración actual al hardware."""
        if not SOAPYSDR_AVAILABLE or isinstance(self._sdr, SimulatedSDR):
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
        """Detiene y cierra el stream RX activo."""
        if not self._stream or not SOAPYSDR_AVAILABLE or isinstance(self._sdr, SimulatedSDR):
            self._stream = None
            return
        try:
            self._sdr.deactivateStream(self._stream)
            self._sdr.closeStream(self._stream)
        except Exception as exc:
            logger.warning("Error cerrando stream RX: %s", exc)
        finally:
            self._stream = None

    def _start_stream(self):
        """Inicia el stream RX."""
        if not SOAPYSDR_AVAILABLE or isinstance(self._sdr, SimulatedSDR):
            return
        self._stream = self._sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        self._sdr.activateStream(self._stream)

    def set_frequency(self, freq_hz: float):
        """Cambia la frecuencia central en Hz."""
        self.center_freq = freq_hz
        if self._sdr:
            if SOAPYSDR_AVAILABLE and not isinstance(self._sdr, SimulatedSDR):
                self._sdr.setFrequency(SOAPY_SDR_RX, self.channel, freq_hz)
            elif isinstance(self._sdr, SimulatedSDR):
                self._sdr.center_freq = freq_hz
        logger.debug(f"Frecuencia: {freq_hz/1e6:.4f} MHz")

    def set_gain(self, gain_db: float):
        """Establece la ganancia en dB."""
        self.gain = gain_db
        if self._sdr and SOAPYSDR_AVAILABLE and not isinstance(self._sdr, SimulatedSDR):
            self._sdr.setGainMode(SOAPY_SDR_RX, self.channel, False)
            self._sdr.setGain(SOAPY_SDR_RX, self.channel, gain_db)
        logger.debug(f"Ganancia: {gain_db} dB")

    # ── Lectura de muestras ─────────────────────────────────────────────────

    def read_samples(self, num_samples: int = 256 * 1024) -> np.ndarray:
        """
        Lee `num_samples` muestras IQ del dispositivo.
        Retorna un array numpy complex64.
        """
        if isinstance(self._sdr, SimulatedSDR):
            return self._sdr.read_samples(num_samples)

        if not self._stream:
            return np.zeros(num_samples, dtype=np.complex64)

        buff   = np.zeros(num_samples, dtype=np.complex64)
        read   = 0
        chunk  = min(num_samples, 65536)

        while read < num_samples:
            to_read = min(chunk, num_samples - read)
            tmp     = np.zeros(to_read, dtype=np.complex64)
            with self._lock:
                sr = self._sdr.readStream(self._stream, [tmp], to_read, timeoutUs=int(1e6))
            if sr.ret > 0:
                buff[read:read + sr.ret] = tmp[:sr.ret]
                read += sr.ret
            elif sr.ret < 0:
                logger.warning(f"readStream error: {sr.ret}")
                break

        return buff

    # ── Info del dispositivo ────────────────────────────────────────────────

    @staticmethod
    def list_devices() -> list[dict]:
        """Lista todos los dispositivos SDR disponibles."""
        if not SOAPYSDR_AVAILABLE:
            return [{"driver": "simulated", "label": "Simulación (sin hardware)"}]
        return [dict(r) for r in SoapySDR.Device.enumerate()]

    @property
    def is_simulated(self) -> bool:
        return isinstance(self._sdr, SimulatedSDR)

    def __repr__(self) -> str:
        status = "simulado" if self.is_simulated else "real"
        return f"SDRDevice(driver={self.driver!r}, freq={self.center_freq/1e6:.3f}MHz, {status})"
