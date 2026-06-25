"""xyz-sdr | ai/

Módulo de IA (FASE 4-5 del roadmap — PENDIENTE).

Estado actual
=============

**PLACEHOLDER.** Este paquete está vacío. Las dependencias opcionales están
declaradas pero ningún código las usa todavía:

- ``pyproject.toml`` → ``[project.optional-dependencies].ai``
- ``requirements-ai.txt``

Paquetes declarados (NO instalados por defecto):

- ``faster-whisper>=1.0``  — transcripción de audio
- ``scikit-learn>=1.3``    — clasificación de modos de modulación
- ``joblib>=1.3``          — paralelismo de inference

Activación
==========

Para activar (experimental):

.. code-block:: bash

    pip install .[ai]
    # o:
    pip install -r requirements-ai.txt

Uso desde la app
================

El módulo expone una API mínima **segura** (no rompe si faltan deps). El flag
``--ai`` en CLI fuerza el enable; sin el flag, se respeta ``[ai]`` del config.

.. code-block:: python

    from ai import is_available, is_enabled, get_status

    if is_enabled(force=cli_flag, config=app_config):
        if is_available():
            ...  # futuro: instanciar Whisper / clasificador
        else:
            ...  # deps no instaladas — degradar a no-op

Implementación futura
====================

Ver ``docs/ai.md`` y ``roadmap.md`` §Fase 4-5. La idea es:

1. Transcripción en tiempo real del demodulado (FM broadcast → texto).
2. Clasificación automática del modo de modulación desde PSD.
3. Sugerencia de frecuencia siguiente ("estabas escuchando X, prueba Y").

**No implementar nada aquí sin antes cerrar Fase 0-3** (DX, testing,
refactor del god class). El AI se beneficia de la base estable.
"""

from __future__ import annotations

from typing import Any, Mapping

__all__ = [
    "is_available",
    "is_enabled",
    "get_status",
    "WHISPER_MODELS",
    "DEFAULT_LANGUAGE",
]

# Modelos Whisper soportados por ``faster-whisper``. Lista cerrada para
# alimentar el ``Select`` del menú de ajustes sin sorpresas.
WHISPER_MODELS: tuple[str, ...] = ("tiny", "base", "small", "medium", "large-v2")
DEFAULT_LANGUAGE: str = "es"


def _try_import_optional() -> dict[str, bool]:
    """Comprueba deps de IA sin llegar a usarlas. Cachea resultado.

    Devuelve un dict con el estado de cada dep opcional:
    ``{"faster_whisper": bool, "sklearn": bool, "joblib": bool}``.
    """
    cache: dict[str, bool] = getattr(_try_import_optional, "_cache", None)
    if cache is not None:
        return cache
    result = {
        "faster_whisper": False,
        "sklearn": False,
        "joblib": False,
    }
    try:
        import faster_whisper  # noqa: F401

        result["faster_whisper"] = True
    except Exception:
        pass
    try:
        import sklearn  # noqa: F401

        result["sklearn"] = True
    except Exception:
        pass
    try:
        import joblib  # noqa: F401

        result["joblib"] = True
    except Exception:
        pass
    _try_import_optional._cache = result  # type: ignore[attr-defined]
    return result


def is_available() -> bool:
    """``True`` si TODAS las deps de IA están instaladas.

    Mientras ``ai/`` sea placeholder, devuelve ``False`` aunque las deps estén
    presentes: no hay motor que cargar. Volverá a ``True`` cuando se implemente
    Fase 4-5.
    """
    return False  # PLACEHOLDER — sin motor todavía.


def is_enabled(*, force: bool = False, config: Mapping[str, Any] | None = None) -> bool:
    """Combina ``--ai`` CLI con ``[ai]`` del config.

    - ``force=True`` (CLI ``--ai``)  → habilita siempre.
    - ``force=False`` → respeta ``config["ai"]`` (cualquier sub-bandera ON).

    Si las deps no están instaladas, devuelve ``False`` aunque ``force=True``
    para evitar imports fatales en runtime.
    """
    if force:
        return is_available()
    if not config:
        return False
    ai_cfg = config.get("ai", {})
    if not isinstance(ai_cfg, Mapping):
        return False
    whisper_on = bool(ai_cfg.get("whisper_enabled", False))
    classifier_on = bool(ai_cfg.get("classifier_enabled", False))
    return is_available() and (whisper_on or classifier_on)


def get_status(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Snapshot para el menú de ajustes y el splash.

    No lanza excepciones. Devuelve un dict con:

    - ``engine_ready``  — motor implementado (siempre ``False`` en placeholder).
    - ``deps``          — dict con cada dep instalada / no.
    - ``whisper_model`` — modelo configurado (default ``"base"``).
    - ``whisper_language`` — idioma configurado (default ``"es"``).
    - ``whisper_enabled``  — switch del config.
    - ``classifier_enabled`` — switch del config.
    """
    deps = _try_import_optional()
    ai_cfg = (config or {}).get("ai", {}) if isinstance(config, Mapping) else {}
    return {
        "engine_ready": is_available(),
        "deps": deps,
        "whisper_model": str(ai_cfg.get("whisper_model", "base")) if isinstance(ai_cfg, Mapping) else "base",
        "whisper_language": str(ai_cfg.get("whisper_language", DEFAULT_LANGUAGE))
        if isinstance(ai_cfg, Mapping)
        else DEFAULT_LANGUAGE,
        "whisper_enabled": bool(ai_cfg.get("whisper_enabled", False)) if isinstance(ai_cfg, Mapping) else False,
        "classifier_enabled": bool(ai_cfg.get("classifier_enabled", False))
        if isinstance(ai_cfg, Mapping)
        else False,
    }