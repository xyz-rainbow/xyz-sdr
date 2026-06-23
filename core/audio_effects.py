"""
xyz-sdr | core/audio_effects.py
Biblioteca de efectos de sonido sintéticos para la terminal UI.
"""

from __future__ import annotations

import numpy as np
import sounddevice as sd
import logging

logger = logging.getLogger(__name__)


class AudioEffects:
    """Generador y reproductor de efectos de sonido sintéticos retro no bloqueantes."""

    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = sample_rate
        self.enabled = True
        self._pregenerate_sounds()

    def _pregenerate_sounds(self):
        sr = self.sample_rate

        # 1. Click (Sintonía / Scroll) - Muy corto y seco (12 ms)
        t_click = np.linspace(0, 0.012, int(0.012 * sr))
        self._sound_click = (np.sin(2 * np.pi * 900 * t_click) * np.exp(-t_click / 0.003) * 0.25).astype(np.float32)

        # 2. Blip (Hover / Selección de botones) - Rápido (35 ms)
        t_blip = np.linspace(0, 0.035, int(0.035 * sr))
        env_blip = np.linspace(1.0, 0.0, len(t_blip))
        self._sound_blip = (np.sin(2 * np.pi * 650 * t_blip) * env_blip * 0.12).astype(np.float32)

        # 3. Chime (Éxito / Ajustes aplicados) - Arpegio ascendente (220 ms)
        t_chime = np.linspace(0, 0.22, int(0.22 * sr))
        n = len(t_chime)
        wave_chime = np.zeros_like(t_chime)
        # Notas: C5 (523Hz), E5 (659Hz), G5 (784Hz), C6 (1046Hz)
        wave_chime[:n//4] = np.sin(2 * np.pi * 523 * t_chime[:n//4])
        wave_chime[n//4:n//2] = np.sin(2 * np.pi * 659 * t_chime[n//4:n//2])
        wave_chime[n//2:3*n//4] = np.sin(2 * np.pi * 784 * t_chime[n//2:3*n//4])
        wave_chime[3*n//4:] = np.sin(2 * np.pi * 1046 * t_chime[3*n//4:])
        env_chime = np.linspace(0.25, 0.0, len(t_chime))
        self._sound_chime = (wave_chime * env_chime).astype(np.float32)

        # 4. Error (Fallo / Entrada inválida) - Tono grave decadente (180 ms)
        t_error = np.linspace(0, 0.18, int(0.18 * sr))
        env_error = np.linspace(0.35, 0.0, len(t_error))
        wave_error = np.sin(2 * np.pi * 130 * t_error) + 0.4 * np.sin(2 * np.pi * 260 * t_error)
        self._sound_error = (wave_error * env_error).astype(np.float32)

        # 5. Startup (Carga completada / Bienvenida) - Barrido ascendente (350 ms)
        t_startup = np.linspace(0, 0.35, int(0.35 * sr))
        f_sweep = np.linspace(350, 1100, len(t_startup))
        env_startup = np.linspace(0.2, 0.0, len(t_startup))
        # Suavizar ataque para evitar clics de audio abruptos
        att_len = int(0.03 * sr)
        env_startup[:att_len] *= np.linspace(0, 1, att_len)
        self._sound_startup = (np.sin(2 * np.pi * f_sweep * t_startup) * env_startup).astype(np.float32)

    def _play_safe(self, data: np.ndarray):
        if not self.enabled:
            return
        try:
            sd.play(data, self.sample_rate, blocking=False)
        except Exception as e:
            logger.debug(f"Efecto de sonido omitido: {e}")

    def play_click(self):
        """Reproduce un clic corto de sintonía."""
        self._play_safe(self._sound_click)

    def play_blip(self):
        """Reproduce un sonido de hover/selección de botón."""
        self._play_safe(self._sound_blip)

    def play_chime(self):
        """Reproduce un chime arpegiado de éxito."""
        self._play_safe(self._sound_chime)

    def play_error(self):
        """Reproduce un sonido de error grave."""
        self._play_safe(self._sound_error)

    def play_startup(self):
        """Reproduce el barrido ascendente de inicio de la app."""
        self._play_safe(self._sound_startup)
