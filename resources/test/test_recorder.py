"""Tests de grabación SigMF/WAV."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from core.recorder import (
    SDRRecorder,
    recording_targets,
    resolve_recordings_dir,
)


def test_resolve_recordings_dir_defaults_to_music():
    path = resolve_recordings_dir(None)
    assert path.name == "xyz-sdr"
    assert path.parent.name in ("Music", "Música")


def test_resolve_recordings_dir_relative_to_project(tmp_path: Path):
    path = resolve_recordings_dir("./recordings", project_root=tmp_path)
    assert path == (tmp_path / "recordings").resolve()


def test_resolve_recordings_dir_absolute(tmp_path: Path):
    custom = tmp_path / "custom"
    assert resolve_recordings_dir(str(custom)) == custom


def test_recording_targets_cw_includes_audio():
    do_iq, do_audio = recording_targets("cw", record_iq=True, record_audio=True)
    assert do_iq is True
    assert do_audio is True


def test_recording_targets_wbfm_both():
    do_iq, do_audio = recording_targets("wbfm", record_iq=True, record_audio=True)
    assert do_iq is True
    assert do_audio is True


def test_recorder_iq_only(tmp_path: Path):
    recorder = SDRRecorder(tmp_path)
    iq_path, wav_path = recorder.start(
        center_freq_hz=100_600_000,
        sample_rate_hz=500_000,
        demod_mode="cw",
        record_iq=True,
        record_audio=False,
    )
    samples = (np.random.randn(512) + 1j * np.random.randn(512)).astype(np.complex64)
    recorder.write_iq(samples)
    iq_final, wav_final = recorder.stop()

    assert iq_final is not None and iq_final.is_file()
    assert wav_final is None


def test_recorder_writes_sigmf_and_wav(tmp_path: Path):
    recorder = SDRRecorder(tmp_path)
    iq_path, wav_path = recorder.start(
        center_freq_hz=100_600_000,
        sample_rate_hz=500_000,
        demod_mode="wbfm",
        audio_rate=48_000,
        record_iq=True,
        record_audio=True,
    )

    samples = (np.random.randn(1024) + 1j * np.random.randn(1024)).astype(np.complex64)
    audio = np.linspace(-0.2, 0.2, 512, dtype=np.float32)

    recorder.write_iq(samples)
    recorder.write_audio(audio)
    iq_final, wav_final = recorder.stop()

    assert iq_final is not None and iq_final.stat().st_size == 1024 * 2 * 4
    assert wav_final is not None and wav_final.is_file()

    meta_path = iq_final.with_suffix(".sigmf-meta")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["global"]["core:sample_rate"] == 500_000.0
