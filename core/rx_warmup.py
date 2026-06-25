"""Límite de muestras IQ durante arranque del stream RX (warmup)."""

from __future__ import annotations

# (iteraciones, tope de muestras por iteración)
RX_WARMUP_TIERS: tuple[tuple[int, int], ...] = (
    (3, 4_096),
    (5, 16_384),
    (5, 65_536),
)

RX_WARMUP_ITERS = sum(count for count, _ in RX_WARMUP_TIERS)
RX_WARMUP_SAMPLE_CAP = max(cap for _, cap in RX_WARMUP_TIERS)


def _warmup_cap_for_iter(iter_index: int) -> int:
    """Tamaño máximo de chunk según la iteración de warmup (0-based)."""
    seen = 0
    for count, cap in RX_WARMUP_TIERS:
        if iter_index < seen + count:
            return cap
        seen += count
    return RX_WARMUP_SAMPLE_CAP


def cap_rx_warmup_samples(requested: int, warmup_iters_left: int) -> tuple[int, int]:
    """
    Limita el tamaño del chunk en las primeras iteraciones RX.

    Returns:
        (muestras_a_leer, warmup_iters_restantes)
    """
    if warmup_iters_left <= 0:
        return requested, 0
    iter_index = RX_WARMUP_ITERS - warmup_iters_left
    cap = _warmup_cap_for_iter(iter_index)
    capped = min(max(int(requested), 1), cap)
    return capped, warmup_iters_left - 1
