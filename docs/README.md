# Documentación — xyz-sdr

Índice de la documentación técnica. El [README](../README.md) cubre instalación, atajos y visión general.

> **Política de idioma:** Esta documentación está escrita mayoritariamente en español, salvo los archivos `architecture.md`, `dsp.md`, `installer.md`, `audio.md` y `audio-presets-research.md` que están en inglés por motivos históricos.

---

## Guías por tema

| Documento | Contenido |
|-----------|-----------|
| [dx-packaging.md](dx-packaging.md) | **run.ps1**, xyz-sdr.cmd, install_app.ps1, perfiles `config/bands/` |
| [observability.md](observability.md) | **StreamStats**, indicador DROP, métricas `--debug` |
| [installer.md](installer.md) | Wizard Express: drivers, PothosSDR, Python `.venv` |
| [hardware.md](hardware.md) | Hardware real vs `--sim`, troubleshooting, QA |
| [architecture.md](architecture.md) | Hilos, mailbox, viewport, pipeline niveles |
| [dsp.md](dsp.md) | Pipeline IQ→audio, demod, `FmDemodState`, lfilter zi |
| [audio.md](audio.md) | Demodulación, cola audio, efectos UI |
| [bandwidth.md](bandwidth.md) | Sample rate IQ, presets, zoom |
| [passband.md](passband.md) | Banda audible (PASS) |
| [audio-presets-research.md](audio-presets-research.md) | Matriz presets, validación |
| [display.md](display.md) | Paleta, auto-level, ColumnLevelTracker |
| [widgets.md](widgets.md) | Timeline, espectro RLE, cascada |
| [configuration.md](configuration.md) | Referencia `defaults.toml`, `[app]`, bandas, bookmarks |
| [recorder.md](recorder.md) | Grabación IQ SigMF + audio WAV: pipeline, formatos, naming, manual (`R` / `(o) GRABAR IQ`) |
| [scanner.md](scanner.md) | Escáner de banda: paso, dwell, SNR passband, histéresis, botón `🔍 ESCANEAR BANDA` |
| [bookmarks.md](bookmarks.md) | Favoritos de frecuencia: `var/bookmarks.toml`, export/import, botón **Guardar Bookmark** |
| [customization.md](customization.md) | Temas CSS, tuning |
| [ai.md](ai.md) | Estado del módulo `ai/` (Fase 4–5 del roadmap, pendiente) |
| [plugins.md](plugins.md) | Sistema de plugins versionado: demodulators, band profiles, drivers |
| [testing.md](testing.md) | Estructura de tests, mapeo test→módulo, fixtures, comandos |
| [uv_runtime.md](uv_runtime.md) | Wrapper de `uv` para venv + pip install (core/uv_runtime.py) |
| [requirements-locking.md](requirements-locking.md) | Lockfiles `requirements*.lock` con `--require-hashes` |
| [logging.md](logging.md) | Logging seguro con Textual: `detach_console_logging`, `var/log/` |
| [installer-i18n.md](installer-i18n.md) | Traducciones del instalador (es/en), API `t()`, añadir idioma |
| [roadmap.md](roadmap.md) | Plan de ruta |

---

## Mapa de módulos → documentación

```
scripts/run.ps1, xyz-sdr.cmd     → dx-packaging.md, hardware.md
setup/install_app.ps1            → dx-packaging.md, installer.md
core/stream_stats.py             → observability.md
core/band_profiles.py            → dx-packaging.md, configuration.md
core/config_store.py             → configuration.md (persist_band_profile)
core/recorder.py                 → recorder.md, configuration.md
core/bookmarks.py                → bookmarks.md, configuration.md
core/device.py                   → observability.md, bandwidth.md, hardware.md
main.py --band                   → dx-packaging.md, configuration.md
tui/app.py (DROP, debug)         → observability.md, display.md
tui/app.py (action_toggle_scan)  → scanner.md, configuration.md
```

---

## Flujo de lectura recomendado

1. **Instalar y lanzar** → [installer.md](installer.md) → [dx-packaging.md](dx-packaging.md)
2. **Hardware y drops** → [hardware.md](hardware.md) → [observability.md](observability.md)
3. **UI y niveles** → [widgets.md](widgets.md) → [display.md](display.md)
4. **Calidad FM / CPU** → [bandwidth.md](bandwidth.md) → [dsp.md](dsp.md)
5. **Configurar** → [configuration.md](configuration.md) → perfiles en `config/bands/`

---

## Tests

```powershell
.\scripts\test.ps1 -q -m "not slow"
python -m pytest resources/test/test_band_profiles.py resources/test/test_stream_stats.py -q
python setup/check_env.py --verbose
```

---

## Diagramas

| Recurso | Ubicación |
|---------|-----------|
| Arquitectura | `resources/svg/architecture.svg` |
| Header / footer | `resources/svg/header.svg`, `footer.svg` |
