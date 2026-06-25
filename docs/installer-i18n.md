# Internacionalización del instalador

`setup/install_i18n.py` (305 líneas) contiene los textos traducidos del instalador y del wizard de setup. Soporta **español (es)** e **inglés (en)**.

> **Decisión:** toda la UI del instalador es traducible. El resto del proyecto (TUI, docs, código) está mayoritariamente en español con archivos históricos en inglés.

---

## Idiomas soportados

| Código | Idioma | Estado |
|--------|--------|--------|
| `es` | Español | Completo |
| `en` | Inglés | Completo |

---

## API pública

### `t(lang: str, key: str, *args) -> str`

Devuelve el texto traducido para `key` en el idioma `lang`. Si el idioma no existe, cae a `es` (español).

```python
from setup.install_i18n import t

msg = t("es", "menu_opt_pothos")
# "Instalar PothosSDR (Configura SoapySDR + PATH automáticamente)"

msg = t("en", "menu_opt_pothos")
# "Install PothosSDR (auto-configure SoapySDR + PATH)"
```

Si `key` no existe, devuelve `[MISSING: <key>]` (visible en logs para detectar gaps).

```python
t("es", "no_existe")  # "[MISSING: no_existe]"
```

### Detección automática de idioma

```python
import locale, os

def detect_language() -> str:
    """Lee LANG/LC_ALL/LANGUAGE; cae a 'es' si no hay match."""
    for var in ("LC_ALL", "LANG", "LANGUAGE"):
        value = os.environ.get(var, "")
        if value:
            return "en" if value.lower().startswith("en") else "es"
    try:
        sys_lang = locale.getlocale()[0] or ""
        return "en" if sys_lang.lower().startswith("en") else "es"
    except Exception:
        return "es"
```

> **Nota:** en Windows, `locale.getlocale()` raramente devuelve algo útil. Por eso se prefiere leer variables de entorno.

---

## Estructura del diccionario

```python
TRANSLATIONS = {
    "es": {
        "menu_opt_sdrplay": "Instalar SDRplay API v3.x",
        "menu_opt_pothos": "Instalar PothosSDR (...)",
        # ... ~150 entradas
    },
    "en": {
        "menu_opt_sdrplay": "Install SDRplay API v3.x",
        "menu_opt_pothos": "Install PothosSDR (...)",
        # ...
    },
}
```

### Categorías de keys

| Prefijo | Categoría | Ejemplo |
|---------|-----------|---------|
| `menu_opt_*` | Opciones del menú principal | `menu_opt_wizard` |
| `wizard_*` | Wizard Express (1→2→3→4) | `wizard_step`, `wizard_done` |
| `update_*` | Actualización desde git | `update_checking`, `update_success` |
| `install_*` | Errores/información de instalación | `install_fail`, `install_success` |
| `path_*` | Configuración de PATH | `path_label`, `path_success` |
| `py_*` | Entorno Python (.venv) | `py_venv_ready`, `py_uv_ready` |
| `diag_*` | Diagnóstico (`check_env.py`) | `diag_running` |
| `status_*` | Estado del entorno | `status_installed`, `status_missing` |

---

## Cómo añadir una traducción

1. Identifica la key que necesitas (busca con `grep -r "t(ctx.lang," setup/`).
2. Añade la entrada en **ambos** idiomas (`es` y `en`) en `TRANSLATIONS`.
3. Si el texto tiene placeholders, usa `str.format()`:

```python
"wizard_step": "Paso {}/{}: {}",  # es
"wizard_step": "Step {}/{}: {}",  # en

# Llamada:
t(lang, "wizard_step", 2, 4, "Instalar Python")
# es → "Paso 2/4: Instalar Python"
# en → "Step 2/4: Instalar Python"
```

4. Si el idioma destino no existe, créalo (`"fr"`, `"de"`, ...) y añade todas las keys.

---

## Cómo añadir un idioma nuevo

1. Define el código (`"fr"`).
2. Copia la sección `es` como base en `TRANSLATIONS["fr"]`.
3. Traduce entrada por entrada.
4. Actualiza `detect_language()` si quieres auto-detección.
5. Documenta aquí la cobertura (completa/parcial).

---

## Tests

Pendiente: tests que verifiquen:
- Cada idioma tiene las mismas keys.
- `t("xx", "key_inexistente")` devuelve `[MISSING: key_inexistente]`.
- `t("fr", "menu_opt_wizard")` con idioma no soportado cae a `es`.

---

## Decisiones y gaps reconocidos

- **Sin gettext/ICU**: dependencias externas añadidas serían pesadas para un proyecto pequeño. `TRANSLATIONS` dict es suficiente.
- **Sin plurales**: el instalador no necesita plurales complicados (e.g. "1 driver / 2 drivers"). Si se necesita, usar `pybabel` o `babel`.
- **Mezcla con texto en código**: algunos `print()` directos tienen strings hardcodeadas en español. Refactor pendiente para que todo pase por `t()`.

---

## Ver también

- [`installer.md`](installer.md) — wizard que consume las traducciones
- [`uv_runtime.md`](uv_runtime.md) — bootstrap del entorno (también traducible)
- [Política de idioma en docs](README.md#política-de-idioma)