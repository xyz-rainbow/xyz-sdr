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

Implementación futura
=====================

Ver ``docs/ai.md`` y ``docs/roadmap.md`` §Fase 4-5. La idea es:

1. Transcripción en tiempo real del demodulado (FM broadcast → texto).
2. Clasificación automática del modo de modulación desde PSD.
3. Sugerencia de frecuencia siguiente ("estabas escuchando X, prueba Y").

**No implementar nada aquí sin antes cerrar Fase 0-3** (DX, testing,
refactor del god class). El AI se beneficia de la base estable.
"""