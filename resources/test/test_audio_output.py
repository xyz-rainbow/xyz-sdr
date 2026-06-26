"""Tests de core/audio_output.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from core.audio_output import AudioOutputQueue, resolve_output_device


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


def test_resolve_output_device_by_index_string():
    assert resolve_output_device("3") == 3


def test_resolve_output_device_by_name_substring():
    fake_devices = [
        {"name": "Microsoft Sound Mapper", "max_output_channels": 2},
        {"name": "Realtek HD Audio", "max_output_channels": 2},
    ]
    with patch("core.audio_output.sd.query_devices", return_value=fake_devices):
        assert resolve_output_device("realtek") == 1
