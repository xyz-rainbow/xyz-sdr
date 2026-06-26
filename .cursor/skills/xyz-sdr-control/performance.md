# xyz-sdr — Rendimiento y diagnóstico (agentes)

## Síntomas usuario

- Lag al scroll en timeline
- TUI congelada con RX + hardware real
- Crash o `OreadStream error: -4`
- Ctrl+B no oculta panel
- Texto fantasma detrás de la TUI

## Cómo medir (agente debe ejecutar)

### 1. Debug en TUI

```powershell
.\scripts\run.ps1 -DebugMode
# o
.\.venv\Scripts\python.exe main.py --debug --auto-rx
```

Log cada ~3 s (`_report_debug_metrics`):

```
[DEBUG] perf 3.0s | disp pub N app M | RX X iter/s proc Yms | UI Z fps draw Wms lat Lms p95 Pms | iq drop D% ov O to T
```

### 2. Benchmark sin TUI interactiva

```powershell
.\.venv\Scripts\python.exe scripts/bench_rx_fps.py --sim --duration 20
.\.venv\Scripts\python.exe scripts/bench_rx_fps.py --duration 25
```

Salida: `var/harness/bench_*.json` — series `ui_fps`, `pub_rate`, `rx_iter_s`, `iq_drop_pct`.

### 3. Headless export

```powershell
.\.venv\Scripts\python.exe main.py --headless-display --auto-rx --sim --debug --display-duration 15
```

## Baseline medido (referencia)

| Escenario | UI FPS | RX iter/s | UI draw | Latencia frame |
|-----------|--------|-----------|---------|----------------|
| Sim 20s | ~8 (cap 10) | ~45–55 | ~2 ms | ~11 ms |
| HW 25s | ~8 | ~55–60 | ~2 ms | ~12–23 ms p95 |

Coalescing: ~80% frames publicados no se pintan (esperado y sano).

## Cuello de botella

1. **Terminal + Rich Text** — espectro/cascada O(width × height) celdas
2. **RX más rápido que UI** — mailbox descarta (OK)
3. **Ratón** — hover timeline → refresh; mitigar `XYZ_SDR_NO_MOUSE=1`
4. **Múltiples refresh reactive** — mitigado en timeline, pendiente en spectrum/waterfall passband assigns

## Bug P0 — Waterfall `_prepend_viewport_row`

**Archivo:** `tui/widgets/waterfall_timeline.py` ~381–393

**Error:**

```
ValueError: could not broadcast input array from shape (2,86) into shape (10,86)
```

**Causa:** `_slice_cache` con pocas filas; widget `height=10`; asignación `self._slice_ring[1:] = self._slice_cache[: height - 1]` sin validar shapes.

**Efecto:** excepción en cada `_flush_display_frames` → cascada rota → presión stream → overflow.

**Fix esperado (para agente implementador):**

- Si `self._slice_cache.shape[0] < height - 1`: `_rebuild_slice_cache()` o pad con NaN
- En `on_resize`: invalidar `_slice_ring` y `_slice_cache`

## Tuning config (rápido)

| Clave | Valor agresivo | Efecto |
|-------|----------------|--------|
| `dsp.display_fps` | 8–10 | Menos ticks UI |
| `display.waterfall_scroll_fps` | 1–2 | Menos filas cascada |
| `dsp.band_cache_cols` | 512 | Menos columnas |
| `dsp.fft_size` | 1024 | Menos CPU RX |
| `app.performance_ui` | true | Cap 10 FPS + cascada 2 |
| Sidebar Ctrl+B | oculto | Más ancho plot |

## Env / scripts

| Acción | Comando |
|--------|---------|
| Sin ratón | `XYZ_SDR_NO_MOUSE=1` (default run.ps1) |
| Con ratón | `XYZ_SDR_MOUSE=1` |
| VOLK warning | `volk_profile` en Pothos (warning Soapy) |

## Optimizaciones código (prioridad)

### P0
- Fix waterfall ring buffer resize
- Tratar errores display repetidos (circuit breaker)

### P1
- `reactive(..., repaint=False)` + batch en spectrum/waterfall
- Cap `plot_width` con downsampling
- `on_resize` coherente en todos los widgets display

### P2
- Render por bloques (menos `Text.append` por celda)
- Modo "spectrum only" (sin cascada)
- Back-pressure RX si UI < 5 FPS

### P3
- Proceso DSP separado / shared memory
- UI web con canvas

## Informe post-benchmark (plantilla agente)

```markdown
## Resultado
[estable / degradado / crash]

## Métricas
- UI FPS promedio:
- RX iter/s:
- IQ drop %:
- Errores log:

## Causa raíz
[architectural / bug específico / config]

## Cambios recomendados
1. P0 ...
2. P1 ...

## Validación
[comandos ejecutados]
```
