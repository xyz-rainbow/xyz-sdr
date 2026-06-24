"""
xyz-sdr | core/stream_stats.py
Contadores de salud del stream IQ (overflows, timeouts, muestras perdidas).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StreamStats:
    """Métricas acumuladas del stream RX."""

    samples_requested: int = 0
    samples_received: int = 0
    overflows: int = 0
    read_errors: int = 0
    timeouts: int = 0
    recoveries: int = 0
    read_calls: int = 0

    @property
    def samples_dropped(self) -> int:
        return max(0, self.samples_requested - self.samples_received)

    @property
    def drop_rate(self) -> float:
        if self.samples_requested <= 0:
            return 0.0
        return self.samples_dropped / self.samples_requested

    def copy(self) -> StreamStats:
        return StreamStats(
            samples_requested=self.samples_requested,
            samples_received=self.samples_received,
            overflows=self.overflows,
            read_errors=self.read_errors,
            timeouts=self.timeouts,
            recoveries=self.recoveries,
            read_calls=self.read_calls,
        )

    @staticmethod
    def delta(before: StreamStats, after: StreamStats) -> StreamStats:
        """Diferencia entre dos instantáneas (ventana de observabilidad)."""
        return StreamStats(
            samples_requested=after.samples_requested - before.samples_requested,
            samples_received=after.samples_received - before.samples_received,
            overflows=after.overflows - before.overflows,
            read_errors=after.read_errors - before.read_errors,
            timeouts=after.timeouts - before.timeouts,
            recoveries=after.recoveries - before.recoveries,
            read_calls=after.read_calls - before.read_calls,
        )
