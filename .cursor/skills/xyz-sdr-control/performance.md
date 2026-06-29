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

### 4. Soak bandwidth (crash al subir BW)

```powershell
.\scripts\soak_bandwidth.ps1
.\scripts\soak_bandwidth.ps1 -RunnerOnly -DurationMin 10
```

JSON: `var/harness/bw_soak_*.json` — campo `display_errors` debe ser 0.

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

## Bug P0 — Waterfall slice ring (BW / resize)

**Archivos:** `tui/widgets/waterfall_timeline.py`, `tui/app.py` (`change_bandwidth`, `_flush_display_frames`)

**Errores típicos:**

```
ValueError: could not broadcast input array from shape (14,118) into shape (14,86)
Error actualizando espectro/cascada: ...
```

**Causas:** historial/`_slice_ring` del BW anterior; `clear_history` sin resetear ring; prepend con width/height distintos tras Ctrl+B o cambio IQ.

**Fix aplicado:**

- `change_bandwidth` → `_invalidate_band_cache()` + reset level tracker antes de `_sync_viewport`
- `clear_history` → `_reset_slice_state()` (ring + metadatos)
- `_prepend_viewport_row` / `_prepend_slice_row` → padding seguro + recrear ring si cambia width
- `_flush_display_frames` → skip si `_bandwidth_changing`

**Verificación:** `.\scripts\soak_bandwidth.ps1` y `pytest resources/test/test_waterfall_stress.py -q`

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
