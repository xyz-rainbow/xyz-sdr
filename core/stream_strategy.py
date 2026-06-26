"""xyz-sdr | core/stream_strategy.py — Fase 1 pre-work.

Contrato de alto nivel para elegir el camino Soapy SDRplay RX más probable de
funcionar, derivado de la evidencia de Fase 0 (matriz de reproducción). Esta
es **infraestructura**, no la implementación completa: las decisiones AUTO se
quedan en ``AUTO`` hasta que la matriz produzca una fila ``result=OK`` (gate
del roadmap §Fase 0).

Activación
==========

Variable de entorno:

- ``XYZ_SDR_SDRPLAY_STREAM_STRATEGY=auto|cf32_minimal|cf32_legacy|cs16_minimal|cs16_legacy``

Si está vacía, mal escrita o ausente → ``AUTO`` (que en esta pre-fase equivale
al comportamiento previo: ``CF32 + minimal``).

Uso esperado (post-Fase 1, cuando el gate esté abierto)
=======================================================

.. code-block:: python

    from core.stream_strategy import (
        read_sdrplay_strategy,
        strategy_to_format_and_mode,
        convert_cs16_to_iq,
    )

    strategy = read_sdrplay_strategy()
    fmt, mode = strategy_to_format_and_mode(strategy)
    if fmt == "CS16" and want_native_iq:
        samples_iq = convert_cs16_to_iq(raw_cs16_buffer)

Diseño
======

- **No toca Soapy ni hardware.** Todo es pure Python / numpy.
- **No modifica** ``core/device.py``. Esa integración llega con el gate Fase 0.
- **Testeable headless** (ver ``resources/test/test_stream_strategy.py``).

Veredicto baseline (roadmap §Fase 0)
====================================

> API 3.15 OK. Fallo en ``SoapySDRPlay3.setupStream`` / ``activateStream``.
> Recompilar el plugin no corrige. La matriz está iterando ``CF32/CS16`` ×
> ``minimal/legacy`` para encontrar la combinación OK que este módulo
> envolverá.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Tuple

import numpy as np

__all__ = [
    "StreamStrategy",
    "STREAM_FORMAT_CF32",
    "STREAM_FORMAT_CS16",
    "STREAM_MODE_MINIMAL",
    "STREAM_MODE_LEGACY",
    "ENV_VAR_NAME",
    "parse_strategy",
    "read_sdrplay_strategy",
    "strategy_to_format_and_mode",
    "convert_cs16_to_iq",
]


# ─── Constantes de contrato ──────────────────────────────────────────────────

ENV_VAR_NAME: str = "XYZ_SDR_SDRPLAY_STREAM_STRATEGY"

# Ejes de la matriz Fase 0 (ver core/sdrplay_stream_matrix.py).
STREAM_FORMAT_CF32: str = "CF32"
STREAM_FORMAT_CS16: str = "CS16"
STREAM_MODE_MINIMAL: str = "minimal"
STREAM_MODE_LEGACY: str = "legacy"


class StreamStrategy(str, Enum):
    """Estrategia de stream SDRplay. ``AUTO`` se resuelve con la matriz Fase 0.

    Hereda de ``str`` para que ``json.dumps(StreamStrategy.AUTO)`` sea legible
    (``"auto"``) sin código custom.
    """

    AUTO = "auto"
    CF32_MINIMAL = "cf32_minimal"
    CF32_LEGACY = "cf32_legacy"
    CS16_MINIMAL = "cs16_minimal"
    CS16_LEGACY = "cs16_legacy"


# Mapa cerrado estrategia → (formato, modo). Cualquier valor fuera de este
# dict debe ser rechazado por ``parse_strategy`` (no se permite drift).
_STRATEGY_AXES: dict[StreamStrategy, tuple[str, str]] = {
    StreamStrategy.AUTO: (STREAM_FORMAT_CF32, STREAM_MODE_MINIMAL),
    StreamStrategy.CF32_MINIMAL: (STREAM_FORMAT_CF32, STREAM_MODE_MINIMAL),
    StreamStrategy.CF32_LEGACY: (STREAM_FORMAT_CF32, STREAM_MODE_LEGACY),
    StreamStrategy.CS16_MINIMAL: (STREAM_FORMAT_CS16, STREAM_MODE_MINIMAL),
    StreamStrategy.CS16_LEGACY: (STREAM_FORMAT_CS16, STREAM_MODE_LEGACY),
}


# ─── Parsing ─────────────────────────────────────────────────────────────────


def parse_strategy(value: str | None) -> StreamStrategy:
    """Parsea un valor textual a ``StreamStrategy``. Tolerante y nunca lanza.

    Acepta mayúsculas/minúsculas, espacios alrededor, prefijos (``"a"`` →
    ``AUTO``) y devuelve ``AUTO`` ante cualquier entrada inválida. Esto evita
    que un usuario con un typo rompa el arranque.
    """
    if value is None:
        return StreamStrategy.AUTO
    token = value.strip().lower()
    if not token:
        return StreamStrategy.AUTO
    # Match exacto primero (rápido y común).
    for member in StreamStrategy:
        if member.value == token:
            return member
    # Match por prefijo (tolerante pero limitado).
    prefix_matches = [m for m in StreamStrategy if m.value.startswith(token)]
    if len(prefix_matches) == 1:
        return prefix_matches[0]
    # Ambigüedad o vacío → fallback seguro.
    return StreamStrategy.AUTO


def read_sdrplay_strategy(env: Mapping[str, str] | None = None) -> StreamStrategy:
    """Lee ``XYZ_SDR_SDRPLAY_STREAM_STRATEGY`` del entorno y la parsea.

    ``env`` opcional para tests (pasa un dict en lugar de tocar el real).
    """
    source = env if env is not None else os.environ
    return parse_strategy(source.get(ENV_VAR_NAME))


# ─── Resolver ────────────────────────────────────────────────────────────────


def strategy_to_format_and_mode(strategy: StreamStrategy) -> Tuple[str, str]:
    """Resuelve una estrategia a ``(formato, modo)`` para ``setupStream``.

    En esta pre-fase, ``AUTO`` cae al default ``CF32 + minimal`` (comportamiento
    histórico). Cuando el gate Fase 0 abra, esta función consultará el último
    ``best_row`` de la matriz para devolver la combinación probada-OK.
    """
    try:
        return _STRATEGY_AXES[strategy]
    except KeyError as exc:
        # Defensa: un enum custom añadido sin actualizar el mapa no debe romper.
        raise ValueError(f"Estrategia no soportada: {strategy!r}") from exc


# ─── CS16 → IQ (pure numpy, sin Soapy) ──────────────────────────────────────


def convert_cs16_to_iq(
    samples_cs16: np.ndarray,
    *,
    out: np.ndarray | None = None,
) -> np.ndarray:
    """Convierte samples Soapy CS16 (int16) a IQ complejo64 normalizado.

    SoapySDR entrega CS16 como pares ``I,Q`` intercalados de 16 bits
    little-endian. Tras leer el buffer, normalizamos a ``±1.0`` (rango Soapy)
    para que el DSP downstream trabaje con la misma escala que CF32.

    Parameters
    ----------
    samples_cs16:
        Array int16 de longitud par (pares IQ intercalados). Si la longitud
        es impar, se ignora el último sample (warning en el log, no raise).
    out:
        Array de salida opcional (forma ``(N//2,)`` dtype ``complex64``).
        Si se pasa, se reutiliza para evitar allocations.

    Returns
    -------
    np.ndarray
        Array ``complex64`` con la mitad de muestras que la entrada (1 IQ por
        par). Cada muestra está normalizada a ``±1.0``.

    Notes
    -----
    CS16 → IQ es una transformación sin pérdida de información: el Soapy SDK
    documenta que los valores CS16 ocupan el rango ``[-32768, 32767]``
    representando el rango analógico ``[-1.0, 1.0]``. La división por 32768
    es el patrón estándar en clientes Soapy.
    """
    if samples_cs16.dtype not in (np.int16, np.uint16):
        raise TypeError(
            f"CS16 → IQ espera dtype int16 o uint16, recibido {samples_cs16.dtype}"
        )
    n = samples_cs16.shape[0]
    if n == 0:
        result = np.empty(0, dtype=np.complex64)
        return result if out is None else np.copyto(out, result)
    pairs = n // 2
    if pairs == 0:
        result = np.empty(0, dtype=np.complex64)
        return result if out is None else np.copyto(out, result)
    iq = samples_cs16[: pairs * 2].reshape(pairs, 2)
    if out is None:
        out = np.empty(pairs, dtype=np.complex64)
    # Casting a float32 evita overflow antes de la división.
    out.real = iq[:, 0].astype(np.float32) / 32768.0
    out.imag = iq[:, 1].astype(np.float32) / 32768.0
    return out


# ─── Type alias ──────────────────────────────────────────────────────────────

# Import diferido para no arrastrar typing.Mapping al top-level sin necesidad.
from typing import Mapping  # noqa: E402