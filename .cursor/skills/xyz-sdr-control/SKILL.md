---
name: xyz-sdr-control
description: >-
  Control operativo del proyecto xyz-sdr (TUI SDR, main.py CLI, SDRplay, RX/display,
  settings, benchmarks, lag/crash). Usar al operar la app, depurar TUI/espectro/cascada,
  medir FPS, cambiar config, ejecutar harness/headless, o implementar fixes de rendimiento
  en este repositorio.
---

# xyz-sdr — Control para agentes

Skill de proyecto (`.cursor/skills/xyz-sdr-control/`). Complementa `mario-agent-protocol` (proceso con Mario); esta skill es el **mapa técnico y operativo** del repo.

**Idioma:** conversación con usuario en español; código, commits, identificadores en inglés.

---

## Cuándo cargar referencias

| Necesidad | Archivo |
|-----------|---------|
| CLI, env vars, config TOML, atajos TUI | [api-reference.md](api-reference.md) |
| Pipeline RX → mailbox → display, archivos clave | [architecture.md](architecture.md) |
| Lag, FPS, bugs conocidos, tuning | [performance.md](performance.md) |
| Run/test/bench/commit como agente | [agent-workflows.md](agent-workflows.md) |

---

## Quick start (agente)

1. **Entorno:** usar `.venv` del repo; en Windows rutas con `[` requieren `Set-Location -LiteralPath`.
2. **Verificar:** `.\.venv\Scripts\python.exe main.py --check`
3. **Lanzar TUI:** `.\scripts\run.ps1` (ratón OFF por defecto vía `XYZ_SDR_NO_MOUSE=1`)
4. **RX manual:** por defecto `auto_start_rx = false` — usuario pulsa **S** o activa en **Esc → Hardware SDR → Auto al abrir**
5. **Métricas:** `.\scripts\run.ps1 -DebugMode` o benchmark sin TUI interactiva (ver abajo)
6. **No commit/push** salvo petición explícita del usuario

---

## Comandos esenciales

```powershell
Set-Location -LiteralPath 'Y:\[Proyectos]\[General]\[Main]\xyz-sdr'

# Entorno + hardware
.\.venv\Scripts\python.exe main.py --check
.\.venv\Scripts\python.exe main.py --list-dev

# TUI normal
.\scripts\run.ps1
.\scripts\run.ps1 -Sim -DebugMode
.\scripts\run.ps1 -AutoRx          # si el script expone --auto-rx vía ExtraArgs
.\.venv\Scripts\python.exe main.py --auto-rx --debug

# Sin splash (depuración)
.\scripts\run.ps1 -NoSplash
.\.venv\Scripts\python.exe main.py --no-splash --sim

# Headless captura (main.py, exporta var/harness/)
.\.venv\Scripts\python.exe main.py --headless-display --auto-rx --sim --debug --display-duration 15

# Harness mínimo espectro/cascada
.\scripts\harness.ps1
.\.venv\Scripts\python.exe main.py --harness --sim

# Benchmark FPS (Textual run_test, JSON en var/harness/)
.\.venv\Scripts\python.exe scripts/bench_rx_fps.py --sim --duration 20
.\.venv\Scripts\python.exe scripts/bench_rx_fps.py --duration 25

# Tests relevantes
.\.venv\Scripts\python.exe -m pytest resources/test/test_rx_display_recovery.py -q
.\.venv\Scripts\python.exe -m pytest resources/test/test_tui_performance_ui.py resources/test/test_frequency_timeline_performance.py -q
```

---

## API de control (resumen)

### `main.py` — flags que el agente debe conocer

| Flag | Efecto |
|------|--------|
| `--sim` | Fuerza driver simulado |
| `--debug` | `_report_debug_metrics` cada ~3 s en log TUI |
| `--auto-rx` / `--no-auto-rx` | Anulan `[app].auto_start_rx` del config |
| `--headless-display` | RX + captura automática, sin TUI interactiva |
| `--harness` | TUI mínima diagnóstico (`tui/harness/`) |
| `--no-splash` | Arranque directo (útil para agentes) |
| `--strict` | Sin fallback silencioso a simulated |
| `--config` | Ruta TOML (default `config/defaults.toml`; merge con `config/local.toml`) |

### Config `[app]` / `[dsp]` / `[display]` (defaults actuales)

```toml
[app]
auto_start_rx = false      # OFF por defecto; toggle en Settings
performance_ui = true      # cap display 10 FPS, cascada inicial 2 FPS

[dsp]
display_fps = 10           # tope timer _flush_display_frames

[display]
waterfall_scroll_fps = 2   # throttle filas cascada
```

### Variables de entorno

| Variable | Efecto |
|----------|--------|
| `XYZ_SDR_NO_MOUSE=1` | Sin hover en timeline (menos lag); default en `run.ps1` |
| `XYZ_SDR_MOUSE=1` | Habilita ratón (Windows solo si no NO_MOUSE) |
| `XYZ_SDR_SKIP_SDRPLAY_PREFLIGHT=1` | Salta preflight SDRplay |

### TUI — atajos críticos

| Tecla | Acción |
|-------|--------|
| `S` | Toggle RX |
| `Esc` | Settings (modal) |
| `Ctrl+B` | Ocultar/mostrar panel controles (sidebar) |
| `P` | Captura display → `var/harness/` (con diagnóstico) |
| `←/→` | Scroll frecuencia |
| `Ctrl+←/→` | Zoom |
| `B` | Focus bandwidth (no confundir con Ctrl+B) |

### Settings → Hardware SDR

- **RX:** switch estado RX actual
- **Auto al abrir:** persiste `app.auto_start_rx` en TOML vía `_persist_config("app", ...)`

---

## Arquitectura display (1 párrafo)

RX worker publica `BandFrame` en `BandFrameMailbox`. El hilo UI drena el frame más reciente en `_flush_display_frames` (intervalo `1/display_fps`). `apply_band_frame_to_widgets` actualiza `SpectrumGraph` + `WaterfallTimeline`. **Nunca** actualizar widgets desde el worker RX.

Preset rendimiento: `PERFORMANCE_DISPLAY_FPS=10`, `PERFORMANCE_WATERFALL_FPS=2`, `action_toggle_sidebar` en `#controls` (`Vertical`, no `Container`).

Timeline: usar `FrequencyTimeline.update_display_state()` (batch, `reactive(..., repaint=False)`).

---

## Bugs / riesgos conocidos (leer antes de tocar display)

1. **P0 — Waterfall resize:** `_prepend_viewport_row` puede fallar si `_slice_cache` tiene menos filas que `_view_height()` → `ValueError: shape (2,N) into (10,N)`. Provoca loop de errores en hardware + `OreadStream error: -4`. Ver [performance.md](performance.md).
2. **Ctrl+B roto** si `query_one("#controls", Container)` — debe ser `Vertical`.
3. **Ghost text consola:** `core/console_utf8.py`, alternate screen, fondos sólidos en TUI.
4. **pytest Windows:** a veces exit code raro; verificar que tests pasen en output.

---

## Métricas de referencia (bench 120×36)

| Modo | UI FPS | RX iter/s | UI draw | Notas |
|------|--------|-----------|---------|-------|
| Sim 20s | ~8 | ~45–55 | ~2 ms | Estable; ~82% frames descartados (coalescing OK) |
| HW 25s | ~8 | ~55–60 | ~2 ms | Errores cascada; IQ drop 0.2–1.5% |

Log debug típico: `[DEBUG] perf 3.0s | RX … iter/s | UI … fps draw …ms lat …ms | iq drop …%`

---

## Checklist agente (tarea típica)

```
- [ ] Leer skill + reference si toca API/config
- [ ] main.py --check o pytest del área
- [ ] Reproducir: bench_rx_fps.py o headless-display
- [ ] Cambio mínimo; convenciones del archivo vecino
- [ ] pytest archivos tocados
- [ ] Informe: Resultado / Cambios / Validación / Riesgos
- [ ] commit/push solo si el usuario lo pide
```

---

## Integración con otros skills

- **mario-agent-protocol:** fases 0–7, gates, español con Mario.
- **Esta skill:** qué ejecutar, dónde está el código, cómo medir FPS, qué no romper.

---

## Archivos que el agente edita con frecuencia

| Área | Archivos |
|------|----------|
| Entry | `main.py`, `scripts/run.ps1` |
| TUI | `tui/app.py`, `tui/widgets/*.py`, `tui/widgets/settings_menu.py` |
| Display sync | `tui/display_sync.py` |
| Config | `config/defaults.toml`, `config/local.toml` (usuario) |
| Tests | `resources/test/test_*` |
| Bench | `scripts/bench_rx_fps.py` |
| Harness | `tui/harness/`, `scripts/harness.ps1` |

Detalle ampliado: [api-reference.md](api-reference.md), [architecture.md](architecture.md), [performance.md](performance.md), [agent-workflows.md](agent-workflows.md).
