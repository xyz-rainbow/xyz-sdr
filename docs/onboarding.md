# Onboarding — "Tus primeros 15 minutos con xyz-sdr"

> Tutorial paso a paso para arrancar en 15 minutos. Asume Windows 10/11 (ruta principal) o Linux.

---

## 0. Requisitos

- **OS:** Windows 10/11 (recomendado) o Linux con `apt`.
- **Python:** 3.9+ (3.11 o 3.12 recomendado).
- **RAM:** 4 GB mínimo (8 GB para FFT grandes).
- **Disco:** 5 GB libres.
- **Hardware SDR** (opcional): SDRplay RSP, RTL-SDR v3, HackRF, Airspy, etc.

---

## 1. Instalación (5 minutos)

### Windows (recomendado)

```powershell
# Clonar el repo
git clone https://github.com/<owner>/xyz-sdr.git
cd xyz-sdr

# Instalar drivers (Express: 1 opción hace todo)
.\setup\install_drivers.ps1
# Seleccionar [1] Instalar o reparar todo
```

Esto instala:
- PothosSDR (SoapySDR runtime + Python 3.9 embebido).
- SDRplay API v3.15 (si tienes RSP).
- `.venv` con todas las dependencias.

### Linux (RTL-SDR / HackRF)

```bash
git clone https://github.com/<owner>/xyz-sdr.git
cd xyz-sdr
sudo apt install soapysdr-tools soapysdr-module-rtlsdr soapysdr-module-hackrf
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

### Sin hardware (modo simulación)

Si aún no tienes SDR, salta el paso de drivers y arranca directamente:

```powershell
.\scripts\run.ps1 -Sim
```

Verás IQ sintético (estaciones FM simuladas, tonos AM, etc.).

---

## 2. Verificar entorno (1 minuto)

```powershell
.\scripts\run.ps1 -Check
```

Output esperado:

```
✅ Python 3.11.5 (compatible)
✅ numpy 1.24.4
✅ scipy 1.10.1
✅ textual 0.62.0
✅ SoapySDR 0.8.1
✅ SDRplay RSP1A detectada
```

Si alguna dependencia falta, ejecuta de nuevo `.\setup\install_drivers.ps1`.

---

## 3. Lanzar la app (10 segundos)

```powershell
# Modo simulación (sin hardware)
.\scripts\run.ps1 -Sim

# Con hardware SDRplay
.\scripts\run.ps1 -Driver sdrplay

# Perfil FM broadcast (88-108 MHz)
.\scripts\run.ps1 -Band fm_broadcast

# Modo verbose (métricas en panel log)
.\scripts\run.ps1 -Sim -DebugMode
```

Verás la TUI:

```
┌─────────────────────────────────────────────────────────────┐
│  ╔══╗ ╦ ╦ ╔═╗    ╔═╗ ╦ ╦ ╔═╗ ╦═╗                            │
│  ║   ╠═╣ ║╣     ║   ║ ║ ║ ║ ╠╦╝                            │
│  ╚═╝ ╩ ╩ ╚═╝    ╚═╝ ╚═╝ ╚═╝ ╩╚═                            │
├─────────────────────────────────────────────────────────────┤
│  [Frequency Timeline]                                       │
│  ─────────────────────────────────────────────              │
│ 88.0          100.6          108.0 MHz                      │
│                                                             │
│  [Spectrum + Waterfall (side by side)]                       │
│  ███▆▄▂▁▁▂▄▆█████▆▄▂▁▁▂▄▆██                                │
│  ▂▃▄▅▆▇█▇▆▅▄▃▂▁▁▂▃▄▅▆▇█▇▆                                 │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  [Sidebar]                                                  │
│   Banda: fm_broadcast                                       │
│   Modo:  wbfm                                               │
│   Vol:   75%   Gan: 40dB                                    │
│   BW:    2.048 MHz  |  📻 100.6 MHz                        │
│   [S] RX on/off                                             │
│   [B] Cambiar BW                                            │
│   [R] Grabar IQ                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Atajos básicos (30 segundos)

| Tecla | Acción |
|-------|--------|
| `←` / `→` | Desplazar sintonía |
| `↑` / `↓` | Ciclar paso de scroll |
| `Ctrl+←/→` | Zoom in/out |
| `Space` | Centrar vista en frecuencia |
| `S` | Iniciar/detener RX |
| `M` | Ciclar modo demod |
| `B` | Selector bandwidth |
| `[` / `]` | Estrechar/ensanchar PASS |
| `G` / `V` | Ganancia / volumen |
| `Esc` | Menú ajustes |
| `Q` | Salir |

**Ratón:** clic y arrastre en spectrum para definir PASS (banda audible). Rueda = scroll. Ctrl+rueda = zoom.

---

## 5. Tu primera sesión FM (3 minutos)

1. Lanza con perfil FM: `.\scripts\run.ps1 -Band fm_broadcast -Sim`
2. Pulsa `S` para iniciar RX (botón RX se pone verde).
3. Pulsa `↑`/`↓` o `←`/`→` para moverte por la banda FM (88-108 MHz).
4. Observa el espectro: picos altos = emisoras activas.
5. Pulsa `M` para alternar entre WBFM y NBFM.
6. Ajusta volumen con `V` + `+`/`-` o `V` + rueda.
7. Pulsa `R` para grabar IQ de la frecuencia actual (formato SigMF en `var/recordings/`).

---

## 6. Próximos pasos

| Quiero… | Ir a |
|---------|------|
| Entender el DSP | [`docs/dsp.md`](dsp.md) |
| Configurar mi propio band profile | [`docs/configuration.md`](configuration.md) §Band profiles |
| Ver métricas y drops | [`docs/observability.md`](observability.md) |
| Contribuir código | [`CONTRIBUTING.md`](../CONTRIBUTING.md) |
| Escribir un plugin | [`docs/plugins.md`](plugins.md) |
| Entender la arquitectura | [`docs/architecture.md`](architecture.md) |
| Troubleshooting de hardware | [`docs/hardware.md`](hardware.md) |

---

## 7. Errores comunes

| Error | Solución |
|-------|----------|
| `SoapySDR no disponible` | Ejecuta `.\setup\install_drivers.ps1` opción 3 |
| `SDRplay: service not running` | `.\setup\install_sdrplay_api.ps1` |
| `No devices found` | Verifica USB, reconecta SDR, prueba `.\scripts\run.ps1 -ListDev` |
| `RuntimeError: textual...` | `pip install textual~=0.60` (versión anclada) |
| Windows console ilegible (UTF-8) | El launcher `run.ps1` lo arregla; no lances `python main.py` directo |

---

## 8. Recursos externos

- [SoapySDR docs](https://github.com/pothosware/SoapySDR/wiki)
- [Textual tutorial](https://textual.textualize.io/tutorial/)
- [NumPy quickstart](https://numpy.org/doc/stable/user/quickstart.html)
- [SciPy signal processing](https://docs.scipy.org/doc/scipy/reference/signal.html)

---

¡Bienvenido al proyecto! Si te atascas, abre un issue en GitHub con el output de `-Check` y `-DebugMode`.