![xyz-sdr Banner](resources/svg/header.svg)

# 🛰️ xyz-sdr — SDR Terminal Controller

> Controlador SDR interactivo en terminal (TUI) de alto rendimiento, optimizado con un motor de visualización alineado (Timeline + Espectro FFT + Cascada), navegación por teclado y controles dinámicos avanzados.

---

## 🚀 Características Clave

* **Visualización Espectral Alineada en 3 Capas**:
  * **`FrequencyTimeline`**: Regla horizontal con ticks adaptativos automáticos y cursor de sintonización. Ofrece un readout digital dinámico que muestra la frecuencia exacta sintonizada (en rojo) o la frecuencia bajo el ratón en hover (en celeste).
  * **`SpectrumGraph`**: Gráfico FFT interactivo en tiempo real con barras de graduación de altura basadas en decibelios.
  * **`WaterfallTimeline`**: Espectrograma en cascada con alineación de frecuencia física e histórica, auto-level por columna y paleta térmica compartida con el espectro.
* **Auto-level por frecuencia** (`display_level_mode = per_column`):
  * Suelo y techo dinámicos por columna para compensar pendientes de ruido en bandas anchas.
  * Modo `global` alternativo (un solo min/max). Ver [docs/display.md](docs/display.md).
* **Control de Bandwidth IQ (Sample Rate)**:
  * Selector **BANDWIDTH** bajo la frecuencia (250 kHz – 8 MHz según hardware).
  * Al cambiar: pausa RX, reconfigura el SDR, adapta el zoom sin mover la sintonía y guarda en `config/defaults.toml`.
  * Atajo `B` para enfocar el selector.
* **Interactividad Híbrida Completa**:
  * **Navegación por Teclado**: Scroll de sintonía con `← / →`, ajuste de pasos (`1k … 5M`) con `↑ / ↓`, zoom con `Ctrl + ← / →` (o `+ / -`), centrado con `Space`.
  * **Control total con Ratón**: Clic en la **timeline** o el **espectro** fija el centro de la banda audible; **arrastra** simétricamente para definir el ancho (overlay verde + métrica `PASS` en la barra de estado). Clic corto sin arrastre = sintonía + ancho por defecto del modo. Rueda del ratón en timeline/espectro/cascada para desplazarte; `Ctrl + Scroll` para zoom.
* **Motor Visual Cyberpunk & Neon de Alta Resolución**:
  * **Gradiente térmico compartido** (`THERMAL_GRADIENT`, 32 paradas): espectro y cascada usan la misma escala de color.
  * **Señalización de Rango Inactivo**: Zonas sin datos históricos con patrón `░`.
  * **Barra de velocidad horizontal**: Fila entre espectro y cascada con FPS `1, 2, 3, 5, 10, 25, 50`.

---

## 🛠️ Arquitectura del Proyecto

![xyz-sdr Architecture](resources/svg/architecture.svg)

```
xyz-sdr/
├── main.py                     # Punto de entrada de la aplicación
├── config/
│   └── defaults.toml           # Configuración inicial por defecto (FFT, sample rate, etc.)
├── core/
│   ├── device.py               # Abstracción hardware SDR (SoapySDR)
│   ├── config_store.py         # Persistencia TOML
│   ├── band_buffer.py          # BandFrame, viewport slice, mailbox
│   ├── display_levels.py       # ColumnLevelTracker (auto-level por frecuencia)
│   ├── dsp.py                  # FFT, filtros, demodulación
│   ├── dsp_profiles.py         # Perfiles DSP por preset IQ
│   ├── audio_output.py         # Salida audio demodulado
│   ├── passband.py             # Límites PASS
│   └── scanner.py              # Escáner espectral (futuro)
├── tui/
│   ├── app.py
│   └── widgets/
│       ├── display_palette.py  # Gradiente térmico compartido
│       ├── frequency_timeline.py
│       ├── spectrum_graph.py
│       ├── waterfall_timeline.py
│       └── settings_menu.py
├── docs/                       # Documentación detallada de desarrollo
│   ├── README.md               # Índice de documentación
│   ├── installer.md            # Wizard Express, drivers, Python 3.9
│   ├── hardware.md             # SDR real vs sim, QA, troubleshooting
│   ├── architecture.md         # Flujo de datos y arquitectura interna
│   ├── dsp.md                  # Pipeline IQ→audio, demod, perfiles
│   ├── audio.md                # Audio demod + efectos UI
│   ├── bandwidth.md            # Presets IQ, zoom, perfiles DSP
│   ├── passband.md             # Banda audible PASS
│   ├── audio-presets-research.md # Matriz presets, validación
│   ├── display.md              # Paleta, auto-level, barra FPS
│   ├── widgets.md              # Componentes visuales
│   ├── configuration.md        # Referencia config/defaults.toml
│   ├── customization.md        # Temas, tuning DSP
│   └── roadmap.md              # Plan de ruta y fases
```

---

## ⌨️ Tabla de Bindings y Accesos Directos

| Tecla | Acción | Alternativa |
| :--- | :--- | :--- |
| `←` / `→` | Desplazar sintonía según el paso actual | Rueda del ratón en Timeline/Espectro/Cascada |
| `↑` / `↓` | Ciclar tamaño del paso de scroll (1 kHz - 5 MHz) | — |
| `ctrl + ←` / `→`| Zoom In / Zoom Out (span visible acotado al bandwidth IQ) | `+` / `-` o `ctrl + rueda ratón` |
| `Space` | Centrar la vista en la frecuencia sintonizada actual | — |
| `S` | Iniciar / Detener la recepción de radio | Botón de interfaz `>> INICIAR RX` |
| `M` | Ciclar modo de demodulación (`wbfm`, `nbfm`, `am`, `usb`, `lsb`, etc.) | Clic directo en la matriz de la interfaz |
| `F` | Enfocar la caja de texto para introducir frecuencia manual | — |
| `B` | Enfocar el selector de bandwidth IQ (sample rate) | Desplegable **BANDWIDTH** |
| `[` / `]` | Estrechar / ensanchar banda audible (PASS) | Arrastre simétrico con ratón |
| `G` | Enfocar el selector de ganancia del hardware | — |
| `V` | Enfocar el selector de volumen de salida de audio | — |
| `Esc` | Abrir menú de ajustes (hardware, squelch, efectos) | — |
| `Q` | Cerrar la aplicación de manera segura | — |

---

## 💾 Instalación y Ejecución rápida

**Requisito:** entorno `.venv` con Python **3.9** (bindings Pothos) o **3.11/3.12** (64-bit). El instalador crea/repara ese entorno automáticamente.

1. **Instalador (Windows)**:
   ```powershell
   .\setup\install_drivers.ps1
   ```
   Menú Express:
   - **[1] Instalar o reparar todo** — recomendado (git pull + drivers + Python + verificación). Log en `var/log/install-*.log`.
   - **[2] Ejecutar xyz-sdr** — cuando el entorno esté listo (usa `--sim` si no hay SDR conectado).
   - **[3] Diagnóstico rápido** — resumen y siguiente paso.
   - **[A] Opciones avanzadas** — pasos sueltos, diagnóstico completo, update git, idioma.

   Modo headless (CI/scripts):
   ```powershell
   .\setup\install_drivers.ps1 --repair --quiet
   .\setup\install_drivers.ps1 --check
   .\setup\install_drivers.ps1 --check --verbose
   ```

2. **Verificar el entorno**:
   ```powershell
   .\scripts\run.ps1 --check
   ```
   O diagnóstico completo: `python setup/check_env.py --verbose`

3. **Listar hardware detectado**:
   ```powershell
   .\scripts\run.ps1 --list-dev
   ```

4. **Verificación manual (Windows)**:
   ```powershell
   SoapySDRUtil --find=driver=sdrplay
   ```

5. **Modo simulado (opcional, mismo `.venv`)**:
   ```powershell
   .\scripts\run.ps1 --sim
   ```

6. **Ejecución normal (hardware SDR)**:
   ```powershell
   .\scripts\run.ps1
   .\scripts\run.ps1 --driver sdrplay --freq 100.6 --gain 40
   ```
   Sin hardware conectado la app **no** entra en simulación automática; usa `--sim` o conecta el SDR.

   **Prefer `.\scripts\run.ps1`** over `python main.py` — the wrapper uses the project `.venv` and preserves CLI flags through Soapy re-exec (see [hardware setup](docs/hardware.md)).

---

## 📖 Documentación Completa

Índice maestro: **[docs/README.md](docs/README.md)**

| Tema | Documento |
|------|-----------|
| Instalador Windows | [docs/installer.md](docs/installer.md) |
| Hardware real vs simulación | [docs/hardware.md](docs/hardware.md) |
| Arquitectura interna | [docs/architecture.md](docs/architecture.md) |
| DSP (IQ → audio) | [docs/dsp.md](docs/dsp.md) |
| Audio demod + efectos UI | [docs/audio.md](docs/audio.md) |
| Bandwidth IQ (presets) | [docs/bandwidth.md](docs/bandwidth.md) |
| Banda audible (PASS) | [docs/passband.md](docs/passband.md) |
| Presets — calidad y QA | [docs/audio-presets-research.md](docs/audio-presets-research.md) |
| Visualización (paleta, niveles) | [docs/display.md](docs/display.md) |
| Widgets (timeline, FFT, cascada) | [docs/widgets.md](docs/widgets.md) |
| Configuración TOML | [docs/configuration.md](docs/configuration.md) |
| Personalización y temas | [docs/customization.md](docs/customization.md) |
| Roadmap | [docs/roadmap.md](docs/roadmap.md) |

### Bandwidth IQ — resumen rápido

1. Usa el desplegable **BANDWIDTH** (o tecla **`B`**) bajo la frecuencia.
2. Elige un preset (250 kHz … 8 MHz según hardware).
3. La app pausa RX, reconfigura el SDR, adapta el zoom y guarda en `config/defaults.toml`.
4. La frecuencia sintonizada y el centro del viewport **no se mueven**.

Presets y lógica interna: [docs/bandwidth.md](docs/bandwidth.md).

---

![xyz-sdr Footer](resources/svg/footer.svg)
