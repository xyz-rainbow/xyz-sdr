# Documentación — xyz-sdr

Índice de la documentación técnica del proyecto. Los archivos viven en `/docs`; el [README](../README.md) del repositorio resume instalación y atajos.

---

## Guías por tema

| Documento | Contenido |
|-----------|-----------|
| [installer.md](installer.md) | Wizard Express Windows: drivers SDRplay, PothosSDR, Python `.venv` |
| [hardware.md](hardware.md) | Hardware real vs `--sim`, Windows/SDRplay, troubleshooting, QA |
| [architecture.md](architecture.md) | Hilos, `BandFrameMailbox`, re-exec Soapy, viewport, dual path espectro/audio |
| [dsp.md](dsp.md) | Pipeline IQ→audio: perfiles, remuestreo, demod, `FmDemodState` |
| [audio.md](audio.md) | Demodulación, AGC FM, cola de audio, efectos UI, `--debug` |
| [bandwidth.md](bandwidth.md) | Sample rate IQ, presets, cambio en caliente, zoom vs BW |
| [passband.md](passband.md) | Banda audible (PASS), arrastre con ratón, límites por modo |
| [audio-presets-research.md](audio-presets-research.md) | Matriz presets, métricas golden, validación |
| [display.md](display.md) | Paleta térmica, auto-level, `ColumnLevelTracker`, barra FPS |
| [widgets.md](widgets.md) | `FrequencyTimeline`, `SpectrumGraph`, `WaterfallTimeline` |
| [configuration.md](configuration.md) | Referencia completa de `config/defaults.toml` |
| [customization.md](customization.md) | Temas CSS, tuning DSP, modificación de widgets |
| [roadmap.md](roadmap.md) | Fases del proyecto y estado actual |

---

## Mapa de módulos → documentación

```
main.py / scripts/run.ps1       → hardware.md, architecture.md, configuration.md
setup/install_drivers.py        → installer.md
setup/check_env.py              → installer.md, hardware.md
core/device.py                  → bandwidth.md, hardware.md, configuration.md
core/dsp.py                     → dsp.md, audio.md, bandwidth.md
core/dsp_profiles.py            → dsp.md, audio-presets-research.md, bandwidth.md
core/band_buffer.py             → architecture.md, widgets.md
core/display_levels.py          → display.md
core/config_store.py            → configuration.md
core/audio_output.py            → audio.md, architecture.md
core/audio_effects.py           → audio.md
core/passband.py                → passband.md
core/soapy_runtime.py           → hardware.md, installer.md
tui/app.py                      → architecture.md, display.md, widgets.md
tui/widgets/display_palette.py  → display.md
tui/widgets/*_timeline.py       → widgets.md
tui/widgets/settings_menu.py    → configuration.md, audio.md, display.md
resources/test/                 → audio-presets-research.md, dsp.md
```

---

## Flujo de lectura recomendado

1. **Instalar / hardware** → [installer.md](installer.md) → [hardware.md](hardware.md)
2. **Entender la UI** → [widgets.md](widgets.md) → [display.md](display.md)
3. **Calidad FM / CPU** → [bandwidth.md](bandwidth.md) → [dsp.md](dsp.md) → [audio-presets-research.md](audio-presets-research.md)
4. **Configurar TOML** → [configuration.md](configuration.md) → [customization.md](customization.md)
5. **Contribuir o depurar** → [architecture.md](architecture.md) → [roadmap.md](roadmap.md)

---

## Diagramas y assets

| Recurso | Ubicación |
|---------|-----------|
| Arquitectura general | `resources/svg/architecture.svg` (README) |
| Captura UI | `docs/assets/ui_capture.svg` |
| Header / footer | `resources/svg/header.svg`, `footer.svg` |

---

## Tests relacionados

```powershell
python -m pytest resources/test -q
python -m pytest resources/test/test_bandwidth_presets.py -q
python setup/check_env.py --verbose
```
