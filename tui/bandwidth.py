"""Helpers para cambio de bandwidth IQ."""

from __future__ import annotations

from core.device import SampleRateError


def validate_sample_rate(device, new_rate: float, current_rate: float) -> str | None:
    """Devuelve mensaje de error o None si el rate es válido."""
    if abs(current_rate - new_rate) < 1.0:
        return None
    if not device.is_sample_rate_supported(new_rate):
        supported = ", ".join(f"{int(r):_}" for r in device.get_supported_sample_rates())
        return f"Bandwidth no soportado. Opciones: {supported}"
    return None


def apply_sample_rate(device, new_rate: float) -> None:
    """Aplica sample rate al dispositivo o lanza SampleRateError."""
    device.set_sample_rate(new_rate)
