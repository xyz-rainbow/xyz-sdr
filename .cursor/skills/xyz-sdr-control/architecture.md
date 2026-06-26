# xyz-sdr — Arquitectura (agentes)

## Vista general

```
main.py
  └─ XyzSDRApp (Textual)
       ├─ SDRDevice (core/device.py) — SoapySDR / simulated
       ├─ RX worker thread — run_rx_iteration (tui/rx_worker.py)
       ├─ BandFrameMailbox (core/band_buffer.py)
       ├─ AudioOutputQueue, ScannerEngine, StorageController
       └─ Widgets: FrequencyTimeline, SpectrumGraph, WaterfallTimeline
```

## Flujo RX → pantalla

```
[RX worker]                    [Main thread / Textual]
     │                                    │
     ├─ read IQ stream                    │
     ├─ FFT + band cache                  │
     ├─ mailbox.publish(frame)            │
     │                                    ├─ set_interval(1/display_fps)
     │                                    ├─ _flush_display_frames()
     │                                    │     └─ consume_if_new(seq)
     │                                    ├─ apply_band_frame_to_widgets()
     │                                    │     ├─ spectrum.set_viewport_cols
     │                                    │     └─ waterfall.add_viewport_row
     │                                    └─ widget.render() → Rich Text
```

**Regla:** coalescing — si RX > display_fps, solo el frame más nuevo se pinta.

## Archivos por responsabilidad

| Módulo | Rol |
|--------|-----|
| `core/device.py` | Apertura SDR, stream, stats, simulated |
| `core/band_buffer.py` | `BandFrame`, mailbox thread-safe |
| `core/dsp.py` | FFT, demod, squelch |
| `tui/rx_worker.py` | Bucle RX una iteración |
| `tui/display_sync.py` | `apply_band_frame_to_widgets`, levels |
| `tui/app.py` | Orquestación, timers, settings, bindings |
| `tui/widgets/frequency_timeline.py` | Regla freq; `update_display_state` batch |
| `tui/widgets/spectrum_graph.py` | Espectro; paint cache |
| `tui/widgets/waterfall_timeline.py` | Cascada; slice ring + rich cache |
| `tui/widgets/settings_menu.py` | Modal ajustes |
| `tui/harness/` | Diagnóstico aislado |
| `core/console_utf8.py` | Alternate screen, anti ghost text |

## Arranque hardware

1. Splash (opcional) → `_init_hardware_async` (@work thread)
2. SDRplay: preflight, enumerate, `recover_sdrplay_enumeration`
3. `_on_hardware_ready` → log, `_maybe_auto_start_rx` si config
4. Fallo: simulated o `SIM·BLOCK` (SDRplay bloqueado)

## Performance UI preset

Constantes en `tui/app.py`:

```python
PERFORMANCE_DISPLAY_FPS = 10
PERFORMANCE_WATERFALL_FPS = 2
SIDEBAR_WIDTH = 32
```

`performance_ui=true` → cap FPS, cascada lenta inicial, log con hint Ctrl+B.

## Textual / reactive

- Reactives con `repaint=False` en timeline → un solo `refresh()` vía `update_display_state`
- Sin `repaint=False`, cada asignación dispara `obj.refresh()` automático (hasta 6× por scroll)

## Tests útiles

| Test | Qué valida |
|------|------------|
| `test_rx_display_recovery.py` | mailbox, auto-RX, stop RX |
| `test_tui_performance_ui.py` | FPS cap, sidebar toggle |
| `test_frequency_timeline_performance.py` | batch update, render cache |
| `test_sdr_display_harness.py` | export harness |

## Docs en repo

- `docs/architecture.md`, `docs/display.md`, `docs/observability.md`
- `docs/hardware.md` — SDRplay, DROP, tuning lag
