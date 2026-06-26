# API de control SDR — mapa de conocimiento

Referencia rápida para desarrolladores y agentes: **qué usar** en cada operación, sin leer todo `tui/app.py`.

Índice: [roadmap-platform.md](roadmap-platform.md) | [hardware.md](hardware.md) | [architecture.md](architecture.md)

---

## Capas

```
┌─────────────────────────────────────────────────────────┐
│  TUI: XyzSDRApp / SdrDisplayHarnessApp                  │
├─────────────────────────────────────────────────────────┤
│  Orquestación: rx_worker, display_sync, storage         │
├─────────────────────────────────────────────────────────┤
│  Hardware: SDRDevice (core/device.py) + sdr_io thread   │
├─────────────────────────────────────────────────────────┤
│  SoapySDR + SDRplay API / drivers                      │
└─────────────────────────────────────────────────────────┘
```

---

## Operaciones frecuentes

| Objetivo | API / módulo | Notas |
|----------|--------------|-------|
| Listar dispositivos | `SDRDevice.list_devices()` | Tras `bootstrap_soapy()` |
| Abrir RSP | `SDRDevice(driver="sdrplay").open(kwargs)` | `run_sdr_io` interno |
| Sintonizar | `device.set_frequency(hz)` | También `viewport_center` en TUI |
| Ganancia | `device.set_gain(db)` | |
| Cambiar BW IQ | `device.set_sample_rate(hz)` | Validar con `is_sample_rate_supported` |
| Iniciar stream | `device.start_stream(timeout=20)` | Solo en worker RX |
| Leer IQ | `device.read_samples(n)` | Timeout 30 s en hardware |
| Detener stream | `device.stop_stream(timeout=5)` | No `shutdown_sdr_io` en stop normal |
| Cerrar | `device.close()` | Al salir / recovery API |
| Publicar frame UI | `BandFrameMailbox.publish` | Worker → main thread |
| Pintar widgets | `apply_band_frame_to_widgets()` | [display_sync.py](../tui/display_sync.py) |
| Diagnóstico | `python -m tui.harness --headless` | [testing.md](testing.md) |
| Salud SDRplay | `diagnose_sdrplay.ps1` | API + plugin + preflight |
| Reinicio API | `restart_sdrplay_service()` | **No** si device Soapy ya abierto |
| Grabar | `SDRRecorder` vía `StorageController` | SigMF + WAV |
| Escaneo | `ScannerEngine` | Requiere RX activo |
| Métricas stream | `device.stream_stats` | [observability.md](observability.md) |

---

## Flujo RX (resumen)

1. Preflight SDRplay (subproceso) — opcional en harness con `--preflight`.
2. `start_stream()` en hilo worker.
3. Bucle: `run_rx_iteration(host)` → `read_samples` → FFT → `mailbox.publish`.
4. Timer UI: `consume_if_new` → `apply_band_frame_to_widgets`.
5. `stop_stream()` → worker join.

---

## Recovery SDRplay (reglas)

1. Si `_sdr` abierto → **no** llamar `is_sdrplay_api_fault()` ni reiniciar API.
2. Tras reinicio API (Esc / timeout) → `close()` + flag `needs_reopen`.
3. Próximo INICIAR RX → `open()` automático antes de `start_stream`.

Implementado en `tui/app.py` y documentado en `test_rx_display_recovery.py`.

---

## Scripts por operación

| Script | Uso |
|--------|-----|
| `scripts/run.ps1` | App principal |
| `scripts/harness.ps1` | Test display + export |
| `scripts/diagnose_sdrplay.ps1` | Auditoría stack |
| `scripts/test_sdrplay_data.py` | IQ/PSD consola (sin TUI) |

---

## Tests de contrato

| Test | Valida |
|------|--------|
| `test_device_stream.py` | open/stream/read |
| `test_rx_display_recovery.py` | recovery sin shutdown agresivo |
| `test_sdr_display_harness.py` | display_ok pipeline |
| `test_recorder.py` | formatos grabación |

---

## Próxima API (`core/sdr_control.py` — plan Fase A)

Fachada unificada prevista:

```python
class SdrSession:
    def open(self, ...) -> None: ...
    def tune(self, hz: float) -> None: ...
    def set_bandwidth(self, hz: float) -> None: ...
    def start_rx(self) -> None: ...
    def stop_rx(self) -> None: ...
    def health(self) -> dict: ...  # stream_stats + api status
```

La TUI y el harness delegarán aquí para evitar duplicar lógica de recovery.
