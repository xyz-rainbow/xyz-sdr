# Plugins — xyz-sdr

Sistema de plugins versionado para extender xyz-sdr con demoduladores, band profiles y drivers SDR sin tocar el código fuente.

> **API version:** `1.0.0`
> **Entry points group:** `xyz_sdr.demodulators`, `xyz_sdr.band_profiles`, `xyz_sdr.sdr_drivers`
> **Módulo:** `core/plugins.py`

---

## ¿Por qué plugins?

El proyecto es pequeño y single-maintainer. Pero los usuarios avanzados querrán:
- Añadir demoduladores (DAB+, LoRa, RDS, FM-Stereo).
- Compartir band profiles personalizados (repetidores locales, ISM bands).
- Probar drivers SDR experimentales sin forkear el repo.

Los plugins resuelven esto via [Python entry points](https://packaging.python.org/en/latest/specifications/entry-points/) — estándar desde Python 3.8.

---

## Tipos de plugins

### 1) Demodulator plugin

Convierte IQ samples (complex64) en audio (float32, mono).

```python
# mi_paquete/dab.py
import numpy as np
from core.plugins import DemodulatorPlugin


class DABDemod:
    name = "dab"
    sample_rate_range = (1_000_000.0, 2_048_000.0)
    audio_rate = 48_000

    def demodulate(self, iq: np.ndarray, **kwargs) -> np.ndarray:
        # tu lógica DAB+ aquí
        return audio_float32


# mi_paquete/__init__.py
def make_dab():
    return DABDemod()
```

Registrar en `pyproject.toml`:

```toml
[project.entry-points."xyz_sdr.demodulators"]
dab = "mi_paquete:make_dab"
```

### 2) Band profile plugin

Devuelve un dict compatible con `config/bands/*.toml`.

```python
# mi_paquete/repeaters.py
from core.plugins import BandProfilePlugin


class MadridRepeaters:
    profile_id = "madrid_repeaters"
    label = "Repetidores Madrid (UHF)"

    def get_profile(self) -> dict:
        return {
            "meta": {"label": "Repetidores Madrid"},
            "device": {"center_freq": 438_500_000},
            "dsp": {"demod_mode": "nbfm"},
        }


def make_madrid():
    return MadridRepeaters()
```

### 3) SDR driver plugin

Alternativa a SoapySDR para hardware exótico.

```python
# mi_paquete/limesdr.py
from core.plugins import SDRDriverPlugin


class LimeSDR:
    driver_name = "limesdr"

    def open(self, **kwargs) -> object:
        # tu wrapper de LimeSuite
        return device
```

---

## Versioning

`PLUGIN_API_VERSION` sigue semver:

| Cambio | Tipo de bump | Ejemplo |
|--------|--------------|---------|
| Añadir campo opcional al protocolo | PATCH (1.0.0 → 1.0.1) | Nuevo atributo `default_gain` |
| Añadir nuevo protocolo | MINOR (1.0.0 → 1.1.0) | Nuevo `AudioEffectPlugin` |
| Cambiar firma de método | MAJOR (1.0.0 → 2.0.0) | `demodulate(iq, **kwargs)` → `demodulate(iq, sample_rate, **kwargs)` |

Si tu plugin depende de la API, declara en tu `pyproject.toml`:

```toml
[project]
name = "mi-xyz-sdr-plugin"
dependencies = [
    "xyz-sdr>=0.2.0",
]

[project.entry-points."xyz_sdr.demodulators"]
dab = "mi_paquete:make_dab"
```

---

## Diagnóstico

```python
# Ver todos los plugins descubiertos
from core.plugins import discover_all_plugins
import pprint
pprint.pprint(discover_all_plugins())
```

Output esperado (sin plugins externos):

```python
{'api_version': '1.0.0',
 'band_profiles': {},
 'demodulators': {},
 'sdr_drivers': {}}
```

Con un plugin `dab` instalado:

```python
{'api_version': '1.0.0',
 'band_profiles': {},
 'demodulators': {'dab': <mi_paquete.dab.DABDemod object at 0x...>},
 'sdr_drivers': {}}
```

---

## Tolerancia a fallos

- Plugin roto al cargar: warning en log, discovery continúa.
- Plugin que no implementa el protocolo: warning, plugin ignorado.
- Entry_points no disponibles (Python <3.8): discovery devuelve dicts vacíos.

---

## Testing tu plugin

```python
# tests/test_mi_plugin.py
import numpy as np
from mi_paquete import DABDemod


def test_dab_demod_produces_audio():
    demod = DABDemod()
    iq = np.random.randn(2048).astype(np.complex64)
    audio = demod.demodulate(iq)
    assert audio.dtype == np.float32
    assert len(audio) > 0
    assert np.isfinite(audio).all()
```

Para test de integración con discovery:

```python
def test_mi_plugin_visible_via_discovery():
    from core.plugins import discover_demodulators
    plugins = discover_demodulators()
    assert "dab" in plugins
```

---

## Roadmap

- **Fase 4-5:** implementar capa `ai/` real (probablemente vía plugins en vez de monolítica).
- **v1.0.0:** plugin contract estabilizado y documentado.
- **Futuro:** registro de plugins via directorio `plugins/` (sin requerir instalación pip).

---

## Ver también

- [`architecture.md`](architecture.md) — cómo encajan los plugins
- [`testing.md`](testing.md) — testing patterns
- [PEP 621 — entry_points](https://packaging.python.org/en/latest/specifications/entry-points/)