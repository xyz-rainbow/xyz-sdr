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


class AudioOutputQueue:
    """Stream de salida con callback; el hilo RX encola chunks sin bloquear."""

    def __init__(
        self,
        sample_rate: int = 48_000,
        blocksize: int = 1024,
        max_chunks: int = 8,
    ):
        self.sample_rate = sample_rate
        self.blocksize = blocksize
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=max_chunks)
        self._volume = 1.0
        self._lock = threading.Lock()
        self._pending = np.zeros(0, dtype=np.float32)
        self._stream: Optional[sd.OutputStream] = None

    def set_volume(self, level: float) -> None:
        with self._lock:
            self._volume = max(0.0, min(1.0, level))

    def _callback(self, outdata, frames, time_info, status) -> None:
        if status:
            logger.debug("Audio callback status: %s", status)

        out = np.zeros(frames, dtype=np.float32)
        pos = 0

        while pos < frames:
            if len(self._pending) == 0:
                try:
                    self._pending = self._queue.get_nowait()
                except queue.Empty:
                    break

            take = min(frames - pos, len(self._pending))
            with self._lock:
                vol = self._volume
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
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(chunk)
            except queue.Full:
                pass

    def _drain_queue(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def start(self) -> None:
        self._pending = np.zeros(0, dtype=np.float32)
        self._drain_queue()
        self._stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.blocksize,
            callback=self._callback,
        )
        self._stream.start()

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
