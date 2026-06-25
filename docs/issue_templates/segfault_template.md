# Plantilla interna — SoapySDRPlay3 stream SEGFAULT (Windows)

**Uso interno xyz-sdr.** No publicar issue en GitHub upstream hasta OK de Mario.

---

## Resumen

- **Hardware:** SDRplay RSP1 (serial: ___)
- **API:** sdrplay_api_api_version ___ (SDR Console: OK / FAIL)
- **Plugin:** SoapySDRPlay3 ___ (path + sha256)
- **Soapy find/probe:** OK / DEGRADED / FAIL
- **Stream RX:** SEGFAULT en paso ___

## Veredicto LOG

> No es hardware ni API rota: find/probe OK; fallo en SoapySDRPlay3 al abrir stream.

## Entorno

```
OS: Windows ___
Python: ___
PothosSDR: ___
SoapySDR Python binding: ___
```

Adjuntar: `var/log/pip-freeze.txt`

## Matriz JSON

Adjuntar: `var/log/sdrplay-matrix-results.zip`

Mejor fila (si alguna OK): ___

Peor fila representativa:

```json
(paste one row)
```

## Evidencia adicional

- [ ] minidump: ___
- [ ] Event Viewer extracto: ___
- [ ] stderr completo subprocess: ___
- [ ] service_events (SDRplayAPIService): ___

## Pasos mínimos para reproducir

1. Cerrar SDRuno / SDR Console
2. `Restart-Service SDRplayAPIService`
3. `.\scripts\sdrplay_stream_matrix.ps1 -OutDir var/log`
4. Observar SEGFAULT en stream_mode ___ format ___

## Repositorio upstream (borrador)

- **Repo:** https://github.com/pothosware/SoapySDRPlay3
- **Título propuesto:** Windows: SEGFAULT on setupStream/activateStream with API 3.15 + RSP1

---

Responsable escalación: ___  
Fecha límite (5 días hábiles tras OK Mario): ___
