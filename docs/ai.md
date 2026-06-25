# Módulo `ai/` — estado del proyecto

> El módulo `ai/` está reservado para una fase futura (Fase 4 del [roadmap](roadmap.md)). Las dependencias bajo `[ai]` están pre-declaradas pero no se instalan por defecto. Para habilitarlas en cuanto se implemente, ejecutar `pip install .[ai]`.

---

## Resumen

| Aspecto | Estado |
|---------|--------|
| Directorio `ai/` | No creado todavía (placeholder) |
| Sección `[ai]` en `pyproject.toml` | Pre-declarada (`faster-whisper`, `scikit-learn`, `joblib`) |
| Sección `[ai]` en `config/defaults.toml` | Pre-declarada (`whisper_*`, `classifier_*`) |
| Código de runtime | Ninguno |
| Tests | Ninguno |

## Activación futura

Cuando se implemente la Fase 4 (Whisper) o Fase 5 (clasificador) del roadmap:

```powershell
# Instalar dependencias opcionales
pip install .[ai]
# o equivalente:
pip install -r requirements-ai.txt
```

Las claves bajo `[ai]` en `config/defaults.toml` están listas para activarse (`whisper_enabled = true`, `classifier_enabled = true`).

## Documentación relacionada

- [roadmap.md](roadmap.md) — Fases 4 y 5 (Whisper y clasificador)
- [configuration.md](configuration.md) §`[ai]` — referencia de claves pre-declaradas