"""
xyz-sdr | core/device.py
Abstracción del hardware SDR usando SoapySDR.
Compatible con: SDRplay RSP1, RTL-SDR, HackRF, Airspy y cualquier dispositivo SoapySDR.
"""

from __future__ import annotations

import logging
import threading
import numpy as np
from typing import Callable, Optional

try:
    import SoapySDR
    from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32
    SOAPYSDR_AVAILABLE = True
except ImportError:
    SOAPYSDR_AVAILABLE = False
    logging.warning("SoapySDR no disponible — usando modo simulación")

logger = logging.getLogger(__name__)


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
        """Abre el dispositivo SDR. Retorna True si éxito."""
        if not SOAPYSDR_AVAILABLE:
            logger.warning("SoapySDR no disponible, usando simulación")
            self._sdr = SimulatedSDR()
            return True

        try:
            self._sdr = SoapySDR.Device(dict(driver=self.driver))
            self._apply_settings()
            self._start_stream()
            logger.info(f"Dispositivo abierto: driver={self.driver}")
            return True
        except Exception as e:
            logger.error(f"No se pudo abrir el dispositivo: {e}")
            logger.info("Usando modo simulación")
            self._sdr = SimulatedSDR()
            return False

    def close(self):
        """Cierra el stream y el dispositivo."""
        with self._lock:
            if self._stream and SOAPYSDR_AVAILABLE:
                try:
                    self._sdr.deactivateStream(self._stream)
                    self._sdr.closeStream(self._stream)
                except Exception:
                    pass
                self._stream = None
            if self._sdr:
                try:
                    self._sdr.close() if hasattr(self._sdr, "close") else None
                except Exception:
                    pass
                self._sdr = None
        logger.info("Dispositivo cerrado")

    # ── Configuración ───────────────────────────────────────────────────────

    def _apply_settings(self):
        """Aplica la configuración actual al hardware."""
        if not SOAPYSDR_AVAILABLE or isinstance(self._sdr, SimulatedSDR):
            return
        self._sdr.setSampleRate(SOAPY_SDR_RX, self.channel, self.sample_rate)
        self._sdr.setFrequency(SOAPY_SDR_RX, self.channel, self.center_freq)
        self._sdr.setGainMode(SOAPY_SDR_RX, self.channel, self.auto_gain)
        if not self.auto_gain:
            self._sdr.setGain(SOAPY_SDR_RX, self.channel, self.gain)

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

    def set_sample_rate(self, rate: float):
        """Establece la tasa de muestreo en Hz."""
        self.sample_rate = rate
        if self._sdr:
            if SOAPYSDR_AVAILABLE and not isinstance(self._sdr, SimulatedSDR):
                self._sdr.setSampleRate(SOAPY_SDR_RX, self.channel, rate)
                # Reiniciar stream para aplicar nuevo sample rate
                if self._stream:
                    self._sdr.deactivateStream(self._stream)
                    self._sdr.closeStream(self._stream)
                self._start_stream()
            elif isinstance(self._sdr, SimulatedSDR):
                self._sdr.sample_rate = rate

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
