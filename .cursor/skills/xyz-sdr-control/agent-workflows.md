# xyz-sdr — Workflows para agentes

## Principios

1. **Ejecutar, no solo sugerir** — correr `main.py --check`, pytest, bench.
2. **Cambio mínimo** — una causa, un diff enfocado.
3. **No commit/push** sin petición explícita.
4. **Windows paths** — `Set-Location -LiteralPath` para rutas con `[`.
5. **Español** al usuario; **inglés** en código/commits.

---

## Workflow A — Verificar que el proyecto arranca

```
1. Set-Location -LiteralPath '<repo>'
2. .\.venv\Scripts\python.exe main.py --check
3. .\.venv\Scripts\python.exe main.py --list-dev
4. (opcional) .\.venv\Scripts\python.exe main.py --sim --no-splash
   → background 10s, comprobar que TUI arranca, matar proceso
```

Éxito: check OK, dispositivo listado o sim arranca.

---

## Workflow B — Reproducir lag / medir FPS

```
1. .\.venv\Scripts\python.exe scripts/bench_rx_fps.py --sim --duration 20 --out var/harness/bench_sim.json
2. .\.venv\Scripts\python.exe scripts/bench_rx_fps.py --duration 25 --out var/harness/bench_hw.json
3. Leer JSON: ui_fps, errores, iq_drop_pct
4. Si HW: buscar en stderr ValueError waterfall o OreadStream -4
5. Redactar informe con plantilla en performance.md
```

Alternativa interactiva: `run.ps1 -DebugMode` + RX manual (S).

---

## Workflow C — Cambiar comportamiento auto-RX

**Requisito típico:** RX manual por defecto; toggle en settings.

Archivos:
- `config/defaults.toml` → `[app] auto_start_rx`
- `tui/app.py` → default `False` en `app_cfg.get("auto_start_rx", False)`
- `tui/widgets/settings_menu.py` → `sw_auto_start_rx`
- `main.py` → `auto_start_rx=None` + flags CLI
- `resources/test/test_rx_display_recovery.py`

Validar:
```powershell
.\.venv\Scripts\python.exe -m pytest resources/test/test_rx_display_recovery.py -q
```

---

## Workflow D — Fix performance TUI (timeline / sidebar)

Archivos:
- `tui/widgets/frequency_timeline.py` — batch, cache, repaint=False
- `tui/app.py` — PERFORMANCE_*, Ctrl+B, `_sync_viewport`
- `config/defaults.toml` — display_fps, waterfall_scroll_fps, performance_ui
- Tests: `test_tui_performance_ui.py`, `test_frequency_timeline_performance.py`

Validar:
```powershell
.\.venv\Scripts\python.exe -m pytest resources/test/test_tui_performance_ui.py resources/test/test_frequency_timeline_performance.py -q
```

---

## Workflow E — Harness / captura display

```
.\scripts\harness.ps1
# o
.\.venv\Scripts\python.exe main.py --harness --sim

.\.venv\Scripts\python.exe main.py --headless-display --auto-rx --sim --display-duration 15 --display-export-dir var/harness/test_run
```

Revisar `report.json` → `display_ok`, `frames_applied`.

---

## Workflow F — Commit (solo si usuario pide)

Paralelo:
```powershell
git status
git diff
git log -5 --oneline
```

Mensaje orientado al **por qué**; HEREDOC o here-string PowerShell.

No incluir: `.coverage`, secrets, `config/local.toml` si tiene datos usuario.

Push solo si lo pide.

---

## Workflow G — Fix waterfall crash (P0 pendiente)

1. Reproducir: `bench_rx_fps.py` sin `--sim`
2. Confirmar stack en `_prepend_viewport_row`
3. Fix: validar shapes antes de asignar ring; rebuild on resize
4. Test nuevo: resize height change con slice_cache pequeño
5. Re-bench HW 25s — sin ValueError loop

---

## Subagentes (cuándo usarlos)

| Tarea | Subagente |
|-------|-----------|
| Explorar repo amplio | `generalPurpose` explore |
| Review post-fix display | `bugbot` o review manual |
| CI/deploy | `deployment-expert` |

Contrato subagente: objetivo, archivos prohibidos, salida esperada (hallazgos + comandos verificación).

---

## Respuesta al usuario (estructura)

1. **Resultado**
2. **Cambios clave**
3. **Validación** (comandos + salida)
4. **Riesgos/pendientes**
5. **Siguiente paso** (solo si obvio)
