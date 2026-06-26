# xyz-sdr — API reference (agentes)

## Entry points

| Comando | Descripción |
|---------|-------------|
| `python main.py` | TUI principal (`tui.app.XyzSDRApp`) |
| `python main.py --harness` | TUI mínima (`tui.harness.app.SdrDisplayHarnessApp`) |
| `python main.py --headless-display` | Auto-RX + export sin UI interactiva |
| `scripts/run.ps1` | Wrapper Windows (.venv, UTF-8, NO_MOUSE default) |
| `scripts/harness.ps1` | → `main.py --harness` |
| `scripts/bench_rx_fps.py` | Benchmark FPS vía `run_test` |

## main.py — argumentos completos

```
--driver, --freq, --gain, --sample-rate, --mode
--sim, --allow-system-python
--check, --list-dev, --diagnose-sdrplay
--config (default config/defaults.toml)
--band (fm_broadcast | airband | pmr446 | hf_lsb)
--debug, --no-splash
--no-auto-rx, --auto-rx
--harness, --headless-display
--display-duration, --display-export-dir, --display-min-frames
--display-preflight
--no-restart-sdrplay-service
--strict, --ai
```

### Resolución `auto_start_rx`

```python
auto_start_rx = None  # lee config [app].auto_start_rx (default False)
if args.no_auto_rx: auto_start_rx = False
elif args.auto_rx: auto_start_rx = True
```

Headless main conserva `auto_start_rx=True` explícito en `_run_headless_main_tui`.

## Config TOML

### Secciones

| Sección | Claves importantes |
|---------|-------------------|
| `[device]` | `driver`, `sample_rate`, `center_freq`, `gain` |
| `[dsp]` | `fft_size`, `display_fps`, `demod_mode`, bandwidths, squelch |
| `[display]` | `waterfall_scroll_fps`, `waterfall_history`, levels, theme |
| `[app]` | `auto_start_rx`, `performance_ui`, `active_band_profile` |
| `[scanner]`, `[recorder]`, `[ai]` | Ver `docs/configuration.md` |

`config/local.toml` se mergea en arranque (override usuario).

### Persistencia desde TUI

```python
app._persist_config("app", auto_start_rx=True)
app._persist_config("dsp", ...)
app._persist_config("display", waterfall_auto_level=...)
```

Delega en `tui.storage.StorageController`.

## XyzSDRApp — API programática

### Constructor (kwargs frecuentes)

```python
XyzSDRApp(
    driver="sdrplay" | "simulated",
    config=dict,
    config_path="config/defaults.toml",
    debug_mode=False,
    auto_start_rx=None | True | False,
    display_diagnostics=False,
    headless_display=False,
    strict=False,
    ai_enabled=False,
)
```

### Propiedades / estado RX

- `_rx_active`, `_hardware_ready`, `_auto_start_rx`
- `_band_mailbox` — `BandFrameMailbox` (publish worker, consume UI)
- `_display_frames_applied`, `_display_sequence`
- `_maybe_auto_start_rx()` — tras hardware ready si `_auto_start_rx`

### Display

- `_flush_display_frames()` — timer `1/display_fps`
- `_apply_display_frame()` → `apply_band_frame_to_widgets()`
- `_report_debug_metrics()` — cada 3 s si `debug_mode`
- `build_display_export_context()` — harness export
- `action_capture_display()` — tecla P

### Performance UI

- `_display_fps_cap()` — min(config, 10) si `performance_ui`
- `_initial_waterfall_speed()` — `display.waterfall_scroll_fps` o 2
- `action_toggle_sidebar()` / `_apply_sidebar_collapsed()` — `#controls` Vertical

### Viewport

- `_sync_viewport()` — `timeline.update_display_state(...)` batch

## SettingsScreen API

| Switch ID | Efecto |
|-----------|--------|
| `sw_auto_start_rx` | Persist `app.auto_start_rx`; si ON y HW listo → `_maybe_auto_start_rx` |
| `set_rx_active` | Aplicar con driver en Hardware |
| `sw_waterfall_auto_level` | Persist display + widget |
| `sw_sound_effects` | `audio_effects.enabled` |

## Harness export

```python
from tui.harness.export import export_display_snapshot, DisplayExportContext
```

Salida típica: `var/harness/<stamp>/` — `report.json`, `spectrum.png`, `waterfall.png`, `ui.svg`, `frame.npz`.

Criterio `display_ok`: `frames_applied >= display_min_frames`.

## bench_rx_fps.py

```bash
python scripts/bench_rx_fps.py [--sim] --duration 30 --width 120 --height 36 --out var/harness/bench.json
```

JSON: `samples[]` con `ui_fps`, `pub_rate`, `rx_iter_s`, `ui_draw_ms_*`, `latency_ms_*`, `iq_drop_pct` (HW).

## TUI bindings (XyzSDRApp.BINDINGS)

```
left/right — scroll freq
up/down — step
ctrl+left/right — zoom
space — center
s — toggle_rx
m — cycle_mode
f/g/v/b — focus widgets
[/] — passband
shift+up/down — waterfall history
r — record
p — capture_display
escape — show_settings
ctrl+b — toggle_sidebar
q / ctrl+q / ctrl+c — quit
```

## Entorno Windows (agente)

```powershell
Set-Location -LiteralPath 'Y:\[Proyectos]\[General]\[Main]\xyz-sdr'
$env:XYZ_SDR_NO_MOUSE = '1'
.\.venv\Scripts\python.exe ...
```

Ruta repo puede fallar con `cd` normal por corchetes en `[Proyectos]`.
