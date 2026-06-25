# xyz-sdr CW Strict — Plugin de ejemplo

Demodulador CW con filtro paso bajo ultra-estrecho (50 Hz) para aislar señales Morse密集 en bandas congestionadas.

> **Estado:** Ejemplo. Demuestra cómo extender xyz-sdr con modos demod custom via entry_points.

## Instalación (desde el repo xyz-sdr)

```powershell
# Desde la raíz de xyz-sdr
pip install -e examples/xyz_sdr_cw_strict

# O instalable como paquete separado (futuro)
pip install xyz-sdr-cw-strict
```

## Uso

Una vez instalado, el modo aparece automáticamente en `discover_demodulators()`:

```python
from core.plugins import discover_demodulators
plugins = discover_demodulators()
cw_strict = plugins["cw_strict"]
audio = cw_strict.demodulate(iq_samples, sample_rate=250_000)
```

Desde la TUI, una vez integrado en core/dsp.py, el modo se elige via `--mode cw_strict`:

```powershell
.\scripts\run.ps1 -Sim -Mode cw_strict
```

## API

```python
class CWStrictDemod:
    name = "cw_strict"
    sample_rate_range = (250_000.0, 1_000_000.0)
    audio_rate = 48_000

    def demodulate(self, iq, **kwargs) -> np.ndarray:
        ...
```

## Cómo funciona

Internamente delega a `core.dsp.demodulate(mode="cw")` con BW 200 Hz, y luego aplica un `low_pass_filter` adicional de 50 Hz. Esto produce un tono CW más limpio y con menos ruido de banda adyacente.

## Desinstalar

```powershell
pip uninstall xyz-sdr-cw-strict
```

## Extender

Para crear tu propio plugin:

```python
from core.plugins import DemodulatorPlugin

class MyDemod:
    name = "my_mode"
    sample_rate_range = (1_000_000.0, 2_048_000.0)
    audio_rate = 48_000

    def demodulate(self, iq, **kwargs) -> np.ndarray:
        return audio

def make_my_demod():
    return MyDemod()
```

Y registra en `pyproject.toml`:

```toml
[project.entry-points."xyz_sdr.demodulators"]
my_mode = "my_pkg:make_my_demod"
```

Ver [`docs/plugins.md`](../../docs/plugins.md) para más detalles.