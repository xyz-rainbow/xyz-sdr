# Handoff Mario — SDRplay stream matrix 0.2

**Fecha:** 2026-06-25  
**Rama:** `feature/sdrplay-matrix-MR`  
**Estado:** Pendiente revisión Mario (sin PR upstream Soapy hasta OK)

---

## Frase clave (veredicto)

> **No es hardware ni API rota: el probe confirma API 3.15. El fallo está en SoapySDRPlay3 al abrir el stream, con el plugin embebido y con el compilado hoy.**

---

## Resultado matriz (hardware RSP1)

| Métrica | Valor |
|---------|-------|
| Filas CF32 | 8 × **SEGFAULT** (`exit_code=3221225477`, `last_step=open`) |
| Filas CS16 | 8 × SKIP (harness pendiente Fase 0.1) |
| Filas OK | **0** |
| API | `sdrplay_api_api_version=3.150000` |
| Python | 3.9.13 (`.venv`) |

**SHA256**

- `sdrPlaySupport.dll`: `c7c4cd3b209bd18591b4f3f7f55650e727f9530bf027d635b6491419e234d00a`
- `sdrplay_api.dll`: `7264e9497080c8cbc8eec27f45139643e2d2e99c5759a802c2f1bd81806e2ddd`

---

## Artefactos adjuntos

| Ubicación | Descripción |
|-----------|-------------|
| GitHub Release (pre-release) | Ver issue #___ o release `sdrplay-matrix-0.2-evidence` |
| `%USERPROFILE%\Downloads\sdrplay-matrix-results-for-mario.zip` | Copia local |
| `var/log/sdrplay-matrix-20260625-044834.json` | Informe completo |

Contenido ZIP: JSON matriz, `pip-freeze.txt`, `python-version.txt`, `service-events.txt`.

---

## Gaps evidencia (próxima iteración)

- `event_log_entries`: vacío (WER sin eventos Application visibles)
- `minidump_path`: vacío (LocalDumps no configurado para `python.exe`)

---

## Decisión solicitada a Mario

- [ ] OK para implementar **CS16** en matriz (Fase 0.1)
- [ ] OK para **escalación upstream** SoapySDRPlay3 (plantilla: `docs/issue_templates/segfault_template.md`)
- [ ] OK para **commit final + PR** rama `feature/sdrplay-matrix-MR`

---

## Referencias

- [docs/sdrplay-matrix.md](sdrplay-matrix.md)
- [roadmap.md](../roadmap.md) — Fase 0.2
