"""Tests de core/audio_output.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from core.audio_output import AudioOutputQueue


def test_enqueue_drops_when_full():
    q = AudioOutputQueue(sample_rate=48_000, max_chunks=1)
    q.enqueue(np.ones(64, dtype=np.float32))
    q.enqueue(np.ones(64, dtype=np.float32))
    assert q.dropped_chunks >= 1


def test_set_volume_clamps():
    q = AudioOutputQueue(sample_rate=48_000)
    q.set_volume(150.0)
    assert q._volume == 1.0
    q.set_volume(-5.0)
    assert q._volume == 0.0
