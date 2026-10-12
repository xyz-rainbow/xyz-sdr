"""
xyz-sdr | core/sounddevice_runtime.py
Lazy sounddevice access and PortAudio teardown for tests/CI.
"""

from __future__ import annotations

import sys
from typing import Any


class SoundDeviceProxy:
    """Defer PortAudio init until a sounddevice API is actually used."""

    def __getattr__(self, name: str) -> Any:
        import sounddevice as _sd

        return getattr(_sd, name)


sd = SoundDeviceProxy()


def terminate_portaudio() -> None:
    """Release PortAudio (best-effort). Safe from pytest teardown."""
    mod = sys.modules.get("sounddevice")
    if mod is None:
        return
    try:
        mod._terminate()
    except Exception:
        pass
