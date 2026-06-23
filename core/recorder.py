"""
xyz-sdr | core/recorder.py
Grabación IQ (SigMF) y audio demodulado (WAV).
"""

from __future__ import annotations

import json
import logging
import threading
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

AUDIO_DEMOD_MODES = frozenset({"wbfm", "nbfm", "am", "usb", "lsb"})


def resolve_recordings_dir(
    configured: str | None = None,
    *,
    project_root: Path | None = None,
) -> Path:
    """
    Resuelve el directorio de grabaciones.

    - Ruta configurada (relativa o absoluta) → se respeta tal cual.
    - Vacío / None → ~/Music/xyz-sdr (o ~/Música/xyz-sdr).
    """
    if configured is not None and str(configured).strip():
        path = Path(configured).expanduser()
        if not path.is_absolute():
            base = project_root if project_root is not None else Path.cwd()
            path = (base / path).resolve()
        return path

    music_root = Path.home() / "Music"
    if not music_root.is_dir():
        music_root = Path.home() / "Música"
    return music_root / "xyz-sdr"


def recording_targets(
    demod_mode: str,
    *,
    record_iq: bool = True,
    record_audio: bool = True,
) -> tuple[bool, bool]:
    """Determina qué streams grabar según modo y config."""
    do_iq = bool(record_iq)
    do_audio = bool(record_audio) and demod_mode in AUDIO_DEMOD_MODES
    return do_iq, do_audio


def _format_freq_tag(freq_hz: float) -> str:
    if freq_hz >= 1e6:
        return f"{freq_hz / 1e6:.3f}MHz"
    if freq_hz >= 1e3:
        return f"{freq_hz / 1e3:.0f}kHz"
    return f"{freq_hz:.0f}Hz"


class SDRRecorder:
    """Graba IQ en SigMF y/o audio demodulado en WAV de forma thread-safe."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self._lock = threading.Lock()
        self._active = False
        self._iq_path: Optional[Path] = None
        self._meta_path: Optional[Path] = None
        self._wav_path: Optional[Path] = None
        self._iq_file = None
        self._wav_file: Optional[wave.Wave_write] = None
        self._meta: dict = {}
        self._audio_rate = 48_000
        self._iq_samples_written = 0
        self._record_iq = True
        self._record_audio = False

    @property
    def active(self) -> bool:
        return self._active

    @property
    def iq_path(self) -> Optional[Path]:
        return self._iq_path

    @property
    def wav_path(self) -> Optional[Path]:
        return self._wav_path

    @property
    def records_iq(self) -> bool:
        return self._record_iq

    @property
    def records_audio(self) -> bool:
        return self._record_audio

    def start(
        self,
        *,
        center_freq_hz: float,
        sample_rate_hz: float,
        demod_mode: str,
        audio_rate: int = 48_000,
        record_iq: bool = True,
        record_audio: bool = False,
    ) -> tuple[Optional[Path], Optional[Path]]:
        """Inicia grabación. Devuelve rutas IQ y WAV (None si ese stream no se graba)."""
        if not record_iq and not record_audio:
            raise ValueError("Debe grabarse al menos IQ o audio")

        with self._lock:
            if self._active:
                self.stop()

            self._record_iq = record_iq
            self._record_audio = record_audio
            self.output_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            tag = f"{_format_freq_tag(center_freq_hz)}_{demod_mode.upper()}"
            base = f"xyz-sdr_{stamp}_{tag}"

            self._iq_path = self.output_dir / f"{base}.sigmf-data" if record_iq else None
            self._meta_path = (
                self.output_dir / f"{base}.sigmf-meta" if record_iq else None
            )
            self._wav_path = self.output_dir / f"{base}.wav" if record_audio else None
            self._audio_rate = audio_rate
            self._iq_samples_written = 0

            self._meta = {
                "global": {
                    "core:datatype": "cf32_le",
                    "core:sample_rate": float(sample_rate_hz),
                    "core:author": "xyz-sdr",
                    "core:description": f"IQ capture {demod_mode.upper()} @ {_format_freq_tag(center_freq_hz)}",
                    "core:recorder": "xyz-sdr",
                    "core:version": "1.0.0",
                },
                "captures": [
                    {
                        "core:sample_start": 0,
                        "core:frequency": float(center_freq_hz),
                        "core:datetime": datetime.now(timezone.utc).strftime(
                            "%Y-%m-%dT%H:%M:%SZ"
                        ),
                    }
                ],
            }

            self._iq_file = (
                open(self._iq_path, "wb") if record_iq and self._iq_path else None
            )
            if record_audio and self._wav_path is not None:
                self._wav_file = wave.open(str(self._wav_path), "wb")
                self._wav_file.setnchannels(1)
                self._wav_file.setsampwidth(2)
                self._wav_file.setframerate(audio_rate)
            else:
                self._wav_file = None

            self._active = True
            if self._iq_path:
                logger.info("Grabación IQ iniciada: %s", self._iq_path)
            if self._wav_path:
                logger.info("Grabación audio iniciada: %s", self._wav_path)
            return self._iq_path, self._wav_path

    def write_iq(self, samples: np.ndarray) -> None:
        """Escribe un bloque IQ complex64 como cf32_le interleaved."""
        if (
            not self._active
            or not self._record_iq
            or self._iq_file is None
            or samples is None
            or len(samples) == 0
        ):
            return

        chunk = np.asarray(samples, dtype=np.complex64).ravel()
        interleaved = np.empty(len(chunk) * 2, dtype=np.float32)
        interleaved[0::2] = chunk.real
        interleaved[1::2] = chunk.imag
        data = interleaved.tobytes()

        with self._lock:
            if self._iq_file:
                self._iq_file.write(data)
                self._iq_samples_written += len(chunk)

    def write_audio(self, audio: np.ndarray) -> None:
        """Escribe audio float32 como PCM16 en el WAV."""
        if (
            not self._active
            or not self._record_audio
            or self._wav_file is None
            or audio is None
            or len(audio) == 0
        ):
            return

        pcm = np.clip(np.asarray(audio, dtype=np.float32).ravel(), -1.0, 1.0)
        pcm16 = (pcm * 32767.0).astype(np.int16)

        with self._lock:
            if self._wav_file:
                self._wav_file.writeframes(pcm16.tobytes())

    def stop(self) -> tuple[Optional[Path], Optional[Path]]:
        """Cierra archivos y escribe metadatos SigMF."""
        with self._lock:
            if not self._active:
                return self._iq_path, self._wav_path

            if self._iq_file:
                try:
                    self._iq_file.close()
                except Exception:
                    pass
                self._iq_file = None

            if self._wav_file:
                try:
                    self._wav_file.close()
                except Exception:
                    pass
                self._wav_file = None

            if self._meta_path and self._meta and self._record_iq:
                self._meta["global"]["core:num_channels"] = 1
                self._meta["captures"][0]["core:sample_count"] = self._iq_samples_written
                try:
                    self._meta_path.write_text(
                        json.dumps(self._meta, indent=2),
                        encoding="utf-8",
                    )
                except Exception as exc:
                    logger.warning("No se pudo escribir SigMF meta: %s", exc)

            self._active = False
            iq_path, wav_path = self._iq_path, self._wav_path
            logger.info(
                "Grabación detenida (IQ=%s, audio=%s, muestras=%d)",
                iq_path,
                wav_path,
                self._iq_samples_written,
            )
            return iq_path, wav_path
