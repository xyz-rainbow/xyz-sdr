# SDRplay stream matrix — reproducción Soapy RX

Harness para probar combinaciones de formato, sample rate y orden de operaciones en **subprocesos aislados** antes de compilar o cambiar runtime en producción.

Índice: [hardware.md](hardware.md) | [installer.md](installer.md) | [roadmap.md](../roadmap.md)

---

## Veredicto baseline (LOG acordado)

> No es hardware ni API rota: el probe confirma API 3.15. El fallo está en **SoapySDRPlay3 al abrir el stream**, con plugin embebido y compilado.

| Capa | Resultado típico |
|------|------------------|
| SDR Console / API nativa | OK |
| Soapy find / probe | OK (probe DEGRADED al cerrar es conocido) |
| Soapy stream RX | SEGFAULT en `setupStream` / `activateStream` |

---

## Precondiciones (checklist)

- [ ] `SDRplayAPIService` → **Running**
- [ ] SDR Console, SDRuno y xyz-sdr **cerrados**
- [ ] RSP1 visible: `SoapySDRUtil --find=driver=sdrplay` → Found device
- [ ] Admin disponible si hay que reiniciar servicio o copiar DLLs
- [ ] Carpetas `var/log/` y `var/log/dumps/` existentes

---

## Ejecución

```powershell
Restart-Service SDRplayAPIService
Start-Sleep -Seconds 10

$env:XYZ_SDR_PREFLIGHT_TIMEOUT = "90"
.\scripts\sdrplay_stream_matrix.ps1 -OutDir var/log
```

Salida:

- `var/log/sdrplay-matrix-YYYYMMDD-HHMMSS.json`
- `var/log/pip-freeze.txt` (generado si falta)
- `var/log/sdrplay-matrix-results.zip` (opcional, script PS1)

Python directo:

```powershell
.\.venv\Scripts\python.exe -m core.sdrplay_stream_matrix --out-dir var/log
```

---

## Buscar binarios en la máquina tester

```powershell
# SDRplay API (Program Files)
Get-ChildItem -Path "C:\Program Files\SDRplay","C:\Program Files (x86)\SDRplay" `
  -Filter "sdrplay_api.dll" -Recurse -ErrorAction SilentlyContinue |
  Select-Object FullName, Length, LastWriteTime

# Plugin Soapy activo
Get-ChildItem -Path "$env:LOCALAPPDATA\xyz-sdr\SoapySDR" -Filter "sdrPlaySupport.dll" -Recurse -ErrorAction SilentlyContinue

# Soapy / sdrplay en .venv
Get-ChildItem -Path .\.venv -Filter "*.dll" -Recurse -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -match "sdrplay|Soapy" }

.\.venv\Scripts\Activate.ps1
python -V
pip freeze > var/log/pip-freeze.txt
```

SHA256:

```powershell
Get-FileHash -LiteralPath "C:\Program Files\SDRplay\API\x64\sdrplay_api.dll" -Algorithm SHA256
Get-FileHash -LiteralPath "$env:LOCALAPPDATA\xyz-sdr\SoapySDR\modules0.8\sdrPlaySupport.dll" -Algorithm SHA256
```

---

## Schema JSON (campos por fila)

| Campo | Descripción |
|-------|-------------|
| `version` | Versión plugin / commit SoapySDRPlay3 |
| `plugin_mtime`, `plugin_path`, `plugin_sha256` | DLL Soapy usado |
| `sdrplay_api_dll_path`, `sdrplay_api_dll_sha256` | API nativa efectiva |
| `sdrplay_api_api_version` | De probe si disponible |
| `python_version`, `pip_freeze_file` | Entorno `.venv` |
| `sample_rate`, `format`, `stream_mode`, `kwargs` | Combinación probada |
| `result` | `OK`, `SEGFAULT`, `FAIL`, `TIMEOUT`, `SKIP` |
| `exit_code`, `last_step`, `stdout`, `stderr` | Salida subprocess |
| `minidump_path`, `event_log_entries`, `service_events` | Evidencia forense (best-effort) |
| `timestamp` | ISO8601 |

Ejemplo:

```json
{
  "version": "0.5.2-6cc3131",
  "plugin_sha256": "...",
  "sdrplay_api_api_version": "3.150000",
  "sample_rate": 500000,
  "format": "CS16",
  "stream_mode": "minimal",
  "result": "SEGFAULT",
  "last_step": "setupStream",
  "timestamp": "2026-06-25T04:12:03Z"
}
```

---

## Ejes de la matriz (Fase 0.1)

| Eje | Valores |
|-----|---------|
| Formato | `CF32`, `CS16` |
| Sample rate | none, 250k, 500k, 768k, 1M, 2M |
| stream_mode | `minimal`, `legacy`, variantes |
| Device kwargs | driver, +serial, +label |
| setupStream | default, channels=[0] |
| Settings | default, agc off, iqcorr off |

---

## Coordinación

1. **Commit/push inicial** con esqueletos antes de compilar plugin.
2. Ejecutar matriz en hardware real (sub-fase 0.2).
3. Notificar a Mario con `var/log/sdrplay-matrix-results.zip`.
4. **No abrir PR ni issue upstream** hasta OK explícito de Mario.

---

## Redistribución legal (resumen)

| Artefacto | En repo `drivers/` |
|-----------|-------------------|
| `sdrPlaySupport.dll` | Sí (MIT, SoapySDRPlay3) |
| Subset `SoapySDR.dll` | Fase 3 — con licencias |
| `sdrplay_api.dll` suelta | **No** — solo instalador oficial |
| Instalador API `.exe` | `resources/installers/win-x64/` (opcional offline) |

Ver [drivers/README.md](../drivers/README.md).
