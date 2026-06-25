"""Tests de core/audio_effects.py con mock de sounddevice.

`AudioEffects` reproduce sonidos sintéticos cortos (click, blip, chime, error, startup)
vía `sounddevice.play(..., blocking=False)`. Estos tests mockean `sounddevice` para
verificar:

- Forma y duración de cada efecto.
- Reproducción no-bloqueante.
- Tolerancia a errores (sounddevice sin device, etc.).
- Flag `enabled=False` silencia todo.

No requiere hardware de audio real.
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest


@pytest.fixture
def mock_sounddevice_play():
    """Mockea sounddevice.play para tests sin audio real."""
    from unittest.mock import MagicMock
    with patch("core.audio_effects.sd") as mock_sd:
        mock_sd.play = MagicMock(return_value=None)
        yield mock_sd


def test_audio_effects_module_imports():
    """El módulo core/audio_effects debe importar sin errores."""
    import core.audio_effects  # noqa: F401


def test_audio_effects_class_exists():
    """AudioEffects debe estar definido."""
    from core.audio_effects import AudioEffects
    assert AudioEffects is not None


def test_audio_effects_pregenerates_sounds(mock_sounddevice_play):
    """Constructor debe pre-generar los 5 efectos."""
    from core.audio_effects import AudioEffects

    effects = AudioEffects(sample_rate=44100)
    assert hasattr(effects, "_sound_click")
    assert hasattr(effects, "_sound_blip")
    assert hasattr(effects, "_sound_chime")
    assert hasattr(effects, "_sound_error")
    assert hasattr(effects, "_sound_startup")
    assert effects.enabled is True


@pytest.mark.parametrize("method_name,expected_duration_s", [
    ("_sound_click",  0.012),
    ("_sound_blip",   0.035),
    ("_sound_chime",  0.22),
    ("_sound_error",  0.18),
    ("_sound_startup", 0.35),
])
def test_audio_effects_durations(mock_sounddevice_play, method_name, expected_duration_s):
    """Cada efecto debe tener la duración esperada (±1 sample)."""
    from core.audio_effects import AudioEffects

    effects = AudioEffects(sample_rate=44100)
    snd = getattr(effects, method_name)
    sr = effects.sample_rate
    expected_samples = int(expected_duration_s * sr)
    # ±1 sample tolerance
    assert abs(len(snd) - expected_samples) <= 1, (
        f"{method_name}: len={len(snd)}, expected≈{expected_samples}"
    )


@pytest.mark.parametrize("method_name", [
    "play_click",
    "play_blip",
    "play_chime",
    "play_error",
    "play_startup",
])
def test_audio_effects_play_methods_call_sd(mock_sounddevice_play, method_name):
    """Cada play_* debe llamar a sounddevice.play exactamente 1 vez."""
    from core.audio_effects import AudioEffects

    effects = AudioEffects(sample_rate=44100)
    play_method = getattr(effects, method_name)
    play_method()

    assert mock_sounddevice_play.play.call_count == 1
    args, kwargs = mock_sounddevice_play.play.call_args
    # Primer arg: ndarray float32
    assert isinstance(args[0], np.ndarray)
    assert args[0].dtype == np.float32
    # Segundo arg: sample_rate
    assert args[1] == 44100
    # blocking=False
    assert kwargs.get("blocking") is False


def test_audio_effects_disabled_silent(mock_sounddevice_play):
    """Si enabled=False, play_* no debe invocar sounddevice.play."""
    from core.audio_effects import AudioEffects

    effects = AudioEffects(sample_rate=44100)
    effects.enabled = False

    effects.play_click()
    effects.play_blip()
    effects.play_chime()
    effects.play_error()
    effects.play_startup()

    assert mock_sounddevice_play.play.call_count == 0


def test_audio_effects_tolerates_sd_exception():
    """Si sounddevice lanza excepción, play_* no debe propagarla."""
    from core.audio_effects import AudioEffects

    with patch("core.audio_effects.sd") as mock_sd:
        mock_sd.play.side_effect = Exception("PortAudioError")

        effects = AudioEffects(sample_rate=44100)
        # No debe lanzar
        effects.play_click()
        effects.play_error()


@pytest.mark.parametrize("sample_rate", [22050, 44100, 48000])
def test_audio_effects_supports_various_sample_rates(mock_sounddevice_play, sample_rate):
    """Distintos sample rates deben funcionar."""
    from core.audio_effects import AudioEffects

    effects = AudioEffects(sample_rate=sample_rate)
    assert effects.sample_rate == sample_rate
    # Tamaño del click escala con sr
    expected_click_samples = int(0.012 * sample_rate)
    assert abs(len(effects._sound_click) - expected_click_samples) <= 1


def test_audio_effects_amplitude_envelope(mock_sounddevice_play):
    """El chime debe decaer en amplitud (envelope lineal descendente)."""
    from core.audio_effects import AudioEffects

    effects = AudioEffects(sample_rate=44100)
    chime = effects._sound_chime
    # El envelope aplicado es np.linspace(0.25, 0.0, len), así que
    # la amplitud al inicio es mayor que al final
    rms_front = np.sqrt(np.mean(chime[:100] ** 2))
    rms_back = np.sqrt(np.mean(chime[-100:] ** 2))
    assert rms_front > rms_back, "Chime no decae: front < back"