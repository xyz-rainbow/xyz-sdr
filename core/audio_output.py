"""
xyz-sdr | core/audio_output.py
Salida de audio demodulado en tiempo real con callback y cola asíncrona.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Optional

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)


def resolve_output_device(spec: str | int | None) -> int | None:
    """Resuelve índice PortAudio/sounddevice para salida. None = dispositivo por defecto."""
    if spec is None or spec == "":
        return None
    if isinstance(spec, int):
        return spec
    text = str(spec).strip()
    if text.isdigit():
        return int(text)
    try:
        devices = sd.query_devices()
    except Exception as exc:
        raise RuntimeError(f"No se pudo enumerar dispositivos de audio: {exc}") from exc
    needle = text.lower()
    matches: list[int] = []
    for index, dev in enumerate(devices):
        if int(dev.get("max_output_channels", 0)) <= 0:
            continue
        name = str(dev.get("name", "")).lower()
        if needle in name:
            matches.append(index)
    if not matches:
        raise RuntimeError(f"Dispositivo de audio no encontrado: {spec!r}")
    if len(matches) > 1:
        logger.warning("Varios dispositivos coinciden con %r; usando índice %s", spec, matches[0])
    return matches[0]


def output_device_label(device: int | None) -> str:
    if device is None:
        try:
            device = sd.default.device[1]
        except Exception:
            return "default"
    try:
        info = sd.query_devices(device)
        return str(info.get("name", device))
    except Exception:
        return str(device)


class AudioOutputQueue:
    """Stream de salida con callback; el hilo RX encola chunks sin bloquear."""

    def __init__(
        self,
        sample_rate: int = 48_000,
        blocksize: int = 1024,
        max_chunks: int = 8,
        device: int | None = None,
    ):
        self.sample_rate = sample_rate
        self.blocksize = blocksize
        self._device = device
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=max_chunks)
        self._volume = 1.0
        self._lock = threading.Lock()
        self._pending = np.zeros(0, dtype=np.float32)
        self._stream: Optional[sd.OutputStream] = None
        self.underrun_count = 0
        self.dropped_chunks = 0

    def set_volume(self, level: float) -> None:
        with self._lock:
            self._volume = max(0.0, min(1.0, level))

    def _callback(self, outdata, frames, time_info, status) -> None:
        if status:
            if status.output_underflow:
                self.underrun_count += 1
            logger.debug("Audio callback status: %s", status)

        out = np.zeros(frames, dtype=np.float32)
        pos = 0

        with self._lock:
            vol = self._volume

        while pos < frames:
            if len(self._pending) == 0:
                try:
                    self._pending = self._queue.get_nowait()
                except queue.Empty:
                    break

            take = min(frames - pos, len(self._pending))
            out[pos : pos + take] = self._pending[:take] * vol
            self._pending = self._pending[take:]
            pos += take

        outdata[:, 0] = out

    def enqueue(self, audio: np.ndarray) -> None:
        if audio is None or len(audio) == 0:
            return
        chunk = np.asarray(audio, dtype=np.float32).ravel()
        try:
            self._queue.put_nowait(chunk)
        except queue.Full:
            self.dropped_chunks += 1
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(chunk)
            except queue.Full:
                self.dropped_chunks += 1

    def _drain_queue(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def reset_stats(self) -> None:
        self.underrun_count = 0
        self.dropped_chunks = 0

    def start(self) -> None:
        self._pending = np.zeros(0, dtype=np.float32)
        self._drain_queue()
        self.reset_stats()
        stream_kwargs: dict = {
            "samplerate": self.sample_rate,
            "channels": 1,
            "dtype": "float32",
            "blocksize": self.blocksize,
            "callback": self._callback,
        }
        if self._device is not None:
            stream_kwargs["device"] = self._device
        self._stream = sd.OutputStream(**stream_kwargs)
        self._stream.start()
        logger.info(
            "AudioOutputQueue started: %s @ %s Hz",
            output_device_label(self._device),
            self.sample_rate,
        )

    def stop(self) -> None:
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self._pending = np.zeros(0, dtype=np.float32)
        self._drain_queue()
