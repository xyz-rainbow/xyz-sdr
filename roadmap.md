# xyz-sdr — Roadmap

Índice de fases para runtime `drivers/`, matriz Soapy RX y desbloqueo SDRplay en Windows.

Documentación detallada: [docs/sdrplay-matrix.md](docs/sdrplay-matrix.md) | [drivers/README.md](drivers/README.md)

---

## Veredicto baseline (LOG — 2026-06)

> **Resumen del instalador:** Entorno de radio listo para ejecución tras reparar USB/API en Windows. RSP1 inicialmente no visible (código 28/45), pero recuperado tras reinstalar API 3.15 y reiniciar el servicio SDRplayAPIService. SoapySDRPlay3 resuelve correctamente la enumeración finalizando en estado "READY FOR HARDWARE" / "All set".
>
> **Fallo previo de RX:** el probe confirma API 3.15. El fallo histórico reside en **SoapySDRPlay3 al abrir el stream**, con plugin embebido y compilado (`0.5.2-6cc3131`).

| Capa | Estado |
|------|--------|
| SDR Console / API nativa | OK |
| Soapy find / probe | OK (probe DEGRADED al cerrar — conocido) |
| Soapy stream RX | **SEGFAULT** en `setupStream` / `activateStream` |
| Recompilar plugin solo | **No corrige** el crash |

---

## Reglas de coordinación

| Regla | Detalle |
|-------|---------|
| Rama feature | `feature/sdrplay-matrix-<initials>` |
| Commit inicial | Esqueletos + docs **antes** de compilar plugin |
| Sub-fase 0.2 | Matriz en hardware real → artefactos en `var/log/` |
| Gate Mario | Sin PR / issue upstream hasta OK explícito |
| Compilar Soapy | Solo dentro de 0.2 (evidencia) o tras gate |

---

## Fase 0 — Matriz de reproducción (EN CURSO)

**Meta:** segfault reproducible con JSON + evidencia forense.

### 0.0 Commit inicial (esqueletos)

| Fichero | Estado |
|---------|--------|
| `core/sdrplay_stream_matrix.py` | Harness subprocess + JSON |
| `scripts/sdrplay_stream_matrix.ps1` | Wrapper PS1 + zip artefactos |
| `docs/sdrplay-matrix.md` | Precondiciones, schema, comandos |
| `drivers/README.md` | Legal + layout portable |
| `resources/runtime/manifest.json` | Plantilla runtime |
| `docs/issue_templates/segfault_template.md` | Plantilla interna upstream |

### 0.1 Ejes de matriz

- Formato: `CF32`, `CS16` (nativo RSP1)
- Sample rate: none, 250k, 500k, 768k, 1M, 2M
- stream_mode: `minimal`, `legacy`
- Device / setupStream kwargs, settings pre-stream

### 0.2 Sub-fase tester (hardware real)

```powershell
Restart-Service SDRplayAPIService
.\scripts\sdrplay_stream_matrix.ps1 -OutDir var/log
# → notificar Mario: var/log/sdrplay-matrix-results.zip
```

**Evidencia obligatoria:** pip freeze, SHA256 DLLs, stderr completo, Event Viewer (best-effort), minidump si existe.

### 0.3 Legal

- `sdrPlaySupport.dll` → OK en `drivers/` (MIT)
- `sdrplay_api.dll` suelta → **no** en repo; instalador oficial
- Subset Soapy → Fase 3 con licencias

### 0.4 Rollback / escalación

- Sin ruta OK → `--sim`, worker subprocess, issue SoapySDRPlay3 (plantilla interna)
- Plazo escalación: 5 días hábiles tras OK Mario

**Criterio éxito:** ≥1 fila `result=OK` con `readStream ret>=0`.

---

## Fase 1 — Workaround ganador (BLOQUEADA hasta gate)

- `StreamStrategy` en `core/device.py`
- `XYZ_SDR_SDRPLAY_STREAM_STRATEGY=auto|…`
- Preflight alineado con matriz
- CS16 → conversión IQ en `read_samples` si aplica

---

## Fase 2 — `drivers/win-x64/` layout

```
drivers/win-x64/
  plugins/sdrPlaySupport.dll
  soapy/                 # Fase 3
  manifest.json
resources/runtime/manifest.json
```

- `core/driver_runtime.py` — rutas bundled
- `bootstrap_soapy()` prioriza `drivers/` > Pothos > AppData

---

## Fase 3 — Subset Soapy mínimo (~50–150 MB)

- `scripts/stage_soapy_runtime.ps1`
- SoapySDR.dll + deps; sin Pothos completo
- `XYZ_SDR_ALLOW_POTHOS_PLUGINS=1` fallback

---

## Fase 4 — Instalador y diagnose

- Wizard: API OK + stream fail → `--matrix`
- `diagnose_sdrplay.py`: `drivers_root`, `stream_strategy`
- Mensajes repair alineados con veredicto LOG

---

## Fase 5 — Tests y CI

| Tipo | Qué |
|------|-----|
| Unitarios | `test_sdrplay_stream_matrix.py` — parser JSON, mocks |
| CI normal | Sin hardware |
| Job manual pre-release | Matriz + zip adjunto — **no** automatizar sin humano |

---

## Fases anteriores (completadas / en repo)

| Fase | Tema | Estado |
|------|------|--------|
| 1 | Fix SDRplay RX crash (minimal activate, preflight) | Implementado |
| 2 | Diagnose probe DEGRADED, timeouts, `--no-probe` | Implementado |
| 2.5 | Lockfiles requirements | Hecho |
| 3 | Plugin contract, `--strict` | Hecho |
| 4 | Onboarding, devcontainer, release-please | Hecho |

---

## Definición de “hecho” global

1. Matriz ejecutada con artefactos completos.
2. RX funcional **o** escalación upstream acordada.
3. Runtime `drivers/` operativo (Fases 2–3).
4. CI unitario + checklist manual documentado.

---

## Acción inmediata

1. Push rama `feature/sdrplay-matrix-*` con esqueletos.
2. Ejecutar sub-fase 0.2 en máquina con RSP1.
3. Esperar OK Mario → commit final / PR.
