# Logging — xyz-sdr

`core/logging_config.py` (38 líneas) gestiona el logging de forma segura para coexistir con **Textual** (que reemplaza stdout/stderr al iniciar la app).

> **El problema:** En Windows, `logging.StreamHandler(sys.stdout)` después de `app.run()` provoca `OSError: [WinError 6] The handle is invalid` porque Textual cierra/reemplaza la consola.

---

## API pública

### `detach_console_logging() -> None`

Quita los handlers que escriben a stdout/stderr **antes** de `app.run()`. Conserva los `FileHandler` (e.g. sesión en `var/log/xyz-sdr-*.log`).

```python
from core.logging_config import detach_console_logging

detach_console_logging()
app.run()  # ya no choca con handlers de consola
```

**Comportamiento:**

1. Itera `logging.getLogger().handlers`.
2. Si un handler es `StreamHandler` **y no** es subclase de `FileHandler` → lo quita y lo cierra.
3. Si no quedan handlers, añade `NullHandler` para silenciar el warning "No handlers could be found".
4. `logging.raiseExceptions = False` — evita tracebacks en errores de logging (e.g. consola cerrada).

### `preserve_session_file_handler() -> None`

Re-adjunta el logger de sesión al root si hace falta propagación. Llamada por el runtime antes de `app.run()`.

```python
logger = logging.getLogger("xyz-sdr.session")  # logger de sesión
preserve_session_file_handler()                # asegura que file handler siga activo
```

---

## Convenciones del proyecto

- **Logger por módulo:** `logger = logging.getLogger(__name__)` (estándar).
- **Session logger:** `logging.getLogger("xyz-sdr.session")` — handlers de archivo en `var/log/`.
- **Niveles:** `DEBUG` (verbose, métricas), `INFO` (eventos normales), `WARNING` (recuperable), `ERROR` (con stacktrace), `CRITICAL` (no se usa).
- **Sin `print()` en producción:** siempre `logger.info(...)` etc.

---

## Ubicación de logs

| Tipo | Path | Rotación |
|------|------|----------|
| Sesión runtime | `var/log/xyz-sdr-<timestamp>.log` | Por sesión (un archivo por ejecución) |
| Install | `var/log/install-<timestamp>.log` | Por sesión de instalador |
| Tests | `var/pytest_cache/` (pytest interno) | N/A |

> **Importante:** `var/log/` está en `.gitignore` (Fase 0). Los logs son locales a cada instalación.

---

## Cómo añadir un sink custom

```python
import logging
from pathlib import Path

def add_sink(log_path: Path, level: int = logging.INFO) -> None:
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logging.getLogger().addHandler(handler)
```

---

## Tests

Pendiente: tests para `detach_console_logging` que mockeen `logging.getLogger()` y verifiquen que solo se quitan `StreamHandler` no-`FileHandler`.

---

## Decisiones y gaps reconocidos

- **Sin rotación automática**: archivos crecen sin límite durante sesiones largas. `var/log/` puede llenarse tras semanas de uso intensivo. Solución futura: `RotatingFileHandler` con `maxBytes=10MB, backupCount=5`.
- **Sin captura remota**: no hay sink para enviar logs a un servicio externo (Sentry, etc.).
- **Sin structured logging**: solo texto plano. Migración futura a `structlog` si se necesita JSON.

---

## Ver también

- [`uv_runtime.md`](uv_runtime.md) — bootstrap del entorno
- [Python logging howto](https://docs.python.org/3/howto/logging.html)
- [`installer.md`](installer.md) — logs de instalación