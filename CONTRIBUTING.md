# Contribuir a xyz-sdr

¡Gracias por el interés en contribuir! xyz-sdr es un controlador SDR (Software Defined Radio) interactivo en terminal escrito en Python, construido sobre **SoapySDR + Textual + NumPy/SciPy**. Aceptamos contribuciones de cualquier tamaño: bugs, features, documentación, tests, infraestructura.

---

## Setup de desarrollo

### 1. Clonar y preparar entorno

```powershell
# Clonar
git clone https://github.com/<owner>/xyz-sdr.git
cd xyz-sdr

# Crear venv
python -m venv .venv

# Instalar dependencias runtime + dev
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

### 2. Verificar que todo funciona

```powershell
# Tests rápidos (excluye 'slow')
.\.venv\Scripts\python.exe -m pytest resources/test/ -q -m "not slow"

# Lanzar en modo simulación (no requiere hardware SDR)
.\scripts\run.ps1 -Sim
```

Si los tests pasan y la app arranca en modo sim, estás listo para contribuir.

> **¿No tienes hardware SDR?** Perfecto. El modo `-Sim` genera IQ sintético. La mayor parte del trabajo de DSP, UI y configs se puede hacer sin hardware.

---

## Convenciones de código

- **Python**: target 3.9+ (CI corre 3.11/3.12).
- **Line length**: 100 caracteres.
- **Indentación**: 4 espacios, no tabs.
- **Imports**:stdlib → third-party → local, separados por línea en blanco.
- **Type hints**: añadir en APIs públicas nuevas; `from __future__ import annotations` permitido.
- **Docstrings**: módulos públicos nuevos deben tener docstring de módulo + docstrings en funciones/classes exportadas.
- **Logging**: usar `logger = logging.getLogger(__name__)`, nunca `print()`.
- **Async**: el código Textual es async; el RX worker corre en thread (`@work(thread=True)`); respeta la frontera — el worker NUNCA toca widgets.

### Estructura de directorios

| Directorio | Qué vive ahí |
|---|---|
| `core/` | Lógica de dominio (DSP, device, recorder, bookmarks, config). NO importa `tui/`. |
| `tui/` | UI Textual (App, widgets, rx_worker). |
| `ai/` | Módulo IA (placeholder hasta Fase 4-5, ver `docs/ai.md`). |
| `setup/` | Instalador Windows-first. |
| `docs/` | Documentación técnica. |
| `resources/test/` | Tests pytest. |
| `scripts/` | Launchers (run.ps1, test.ps1). |

---

## Tests

### Dónde van

Todos los tests viven en `resources/test/` con naming `test_<module>.py`.

### Convenciones

- **Fixtures reutilizables** van en `resources/test/conftest.py` (synthetic_psd, flat_band_cols, etc.).
- **Aislamiento**: usar `tmp_path`, `monkeypatch`, `MagicMock`, `patch.object`. Nunca depender de estado global.
- **Marcadores disponibles**:
  - `@pytest.mark.slow` — tests que tardan varios segundos.
  - `@pytest.mark.integration` — requieren hardware o red (declarado pero poco usado todavía).
- **Cobertura**: `--cov=core --cov=setup --cov=tui` en CI; umbral actual `--cov-fail-under=55` (subida gradual 40 → 45 → 48 → 50 → 51 → 55; próximos PRs deberían apuntar a 60+ cubriendo `tui/app.py` Textual god class, `core/sdrplay_forensics.py` parsers, `setup/windows_installers.py` download/installer).
- **No romper tests existentes**: corre `python -m pytest resources/test/ --co` antes y después para confirmar.

### Comandos útiles

```powershell
# Suite completa (puede tardar)
.\scripts\test.ps1

# Solo rápidos (iteración)
.\scripts\test.ps1 -q -m "not slow"

# Un test específico
.\.venv\Scripts\python.exe -m pytest resources/test/test_dsp.py -v

# Con cobertura
.\.venv\Scripts\python.exe -m pytest resources/test/ --cov=core --cov=setup --cov=tui --cov-report=term-missing
```

---

## Formato de Pull Requests

### Conventional Commits (sugerido)

```
feat: añadir demodulador DAB+
fix: squelch se quedaba pegado tras cambiar de banda
docs: clarificar uso de auto_record en recorder.md
test: smoke test para tui/app.py en modo simulado
refactor: extraer scanner a core/scanner.py
chore: bump textual a ~=0.65
```

Tipos: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `perf`, `ci`, `build`.

### Reglas

- **Un PR = un cambio cohesivo**. Si tocas DSP y UI en el mismo PR, probablemente son dos PRs.
- **Título < 72 chars**.
- **Descripción con "por qué"** (motivación, issue enlazado) y **"qué"** (resumen de cambios).
- **CI debe pasar** antes de pedir review.
- **Tests añadidos** para código nuevo. Sin excepción.
- **Documentación actualizada** si cambias comportamiento visible (`docs/configuration.md`, README, etc.).

### Checklist

Usa la plantilla `.github/PULL_REQUEST_TEMPLATE.md` (se rellena automáticamente al abrir PR).

---

## Cómo reportar bugs

Abre un issue con la plantilla **🐛 Bug report** e incluye:

- **Python version** (`python --version`).
- **SO** (Windows 10/11, Ubuntu 22.04, macOS 14, etc.).
- **Hardware SDR** (SDRplay RSP1A, RTL-SDR v3, etc.) o "simulated".
- **Versión de xyz-sdr** (`git describe --tags` o commit hash corto).
- **Pasos para reproducir** (mínimos).
- **Comportamiento esperado vs actual**.
- **Logs** relevantes (de `var/log/install-*.log` o salida de `--debug`).
- **Screenshots** si es un bug visual de la TUI.

---

## Idioma de contribuciones

- **Código**: identificadores en inglés (`def demodulate_fm`, no `def demodular_fm`). Comentarios y docstrings pueden ser español o inglés.
- **Documentación**: mayoritariamente en español (ver `docs/README.md` para la política completa). Aceptamos PRs en inglés también.
- **Issues y PRs**: español o inglés, lo que prefieras.
- **Commits**: inglés recomendado (Conventional Commits).

---

## Áreas donde más ayuda necesitamos

Si no sabes por dónde empezar, mira los `Gaps reconocidos` en:

- `docs/recorder.md` — auto_record, rotación, formato `.raw`/`.wav` para IQ.
- `docs/scanner.md` — refactor a `core/scanner.py`, binding de teclado, tests headless.
- `docs/architecture.md` — opciones de refactor del god class.
- `.mavis/plans/deliverables/final_report.md` — informe completo de deuda técnica.

O simplemente busca `TODO` en el código (`grep -r "TODO" core/ tui/`).

---

## Contacto

- **Issues**: GitHub Issues.
- **Discusiones de diseño**: GitHub Discussions (si está habilitado) o issue con etiqueta `discussion`.

---

## Licencia

Por definir — consulta el archivo `LICENSE` en la raíz. Si no existe, pregunta antes de contribuir código que no quieras relicenciar.