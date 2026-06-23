![xyz-sdr Banner](resources/svg/header.svg)

# 🛰️ xyz-sdr — SDR Terminal Controller

> Controlador SDR interactivo en terminal (TUI) de alto rendimiento, optimizado con un motor de visualización alineado (Timeline + Espectro FFT + Cascada), navegación por teclado y controles dinámicos avanzados.

---

## 🚀 Características Clave

* **Visualización Espectral Alineada en 3 Capas**:
  * **`FrequencyTimeline`**: Regla horizontal con ticks adaptativos automáticos y cursor de sintonización. Ofrece un readout digital dinámico que muestra la frecuencia exacta sintonizada (en rojo) o la frecuencia bajo el ratón en hover (en celeste).
  * **`SpectrumGraph`**: Gráfico FFT interactivo en tiempo real con barras de graduación de altura basadas en decibelios.
  * **`WaterfallTimeline`**: Espectrograma en cascada con alineación de frecuencia física e histórica, permitiendo scroll y zoom sin deformar ni perder la trayectoria de las señales.
* **Control de Bandwidth IQ (Sample Rate)**:
  * Selector **BANDWIDTH** bajo la frecuencia (250 kHz – 8 MHz según hardware).
  * Al cambiar: pausa RX, reconfigura el SDR, adapta el zoom sin mover la sintonía y guarda en `config/defaults.toml`.
  * Atajo `B` para enfocar el selector.
* **Interactividad Híbrida Completa**:
  * **Navegación por Teclado**: Scroll de sintonía con `← / →`, ajuste de pasos (`1k … 5M`) con `↑ / ↓`, zoom con `Ctrl + ← / →` (o `+ / -`), centrado con `Space`.
  * **Control total con Ratón**: Clic en la **timeline** o el **espectro** fija el centro de la banda audible; **arrastra** simétricamente para definir el ancho (overlay verde + métrica `PASS` en la barra de estado). Clic corto sin arrastre = sintonía + ancho por defecto del modo. Rueda del ratón en timeline/espectro/cascada para desplazarte; `Ctrl + Scroll` para zoom.
* **Motor Visual Cyberpunk & Neon de Alta Resolución**:
  * **Gradiente de Intensidad de 32 pasos**: Representación visual de señales débiles que se desvanecen gradualmente a negro absoluto (simulando opacidad por decibelios), transitando por cian, verde, amarillo, naranja, rojo vivo y blanco puro para señales en saturación máxima.
  * **Señalización de Rango Inactivo**: Las zonas fuera de la tasa de muestreo del hardware o sin datos históricos se renderizan con un elegante patrón de sombreado (`░`) para denotar inactividad de forma intuitiva.
  * **Barra de Velocidad Vertical Integrada**: Barra lateral derecha ultradelgada para cambiar los FPS de la cascada (`1, 2, 3, 5, 10, 25, 50`) con realce visual verde esmeralda para la opción activa.

---

## 🛠️ Arquitectura del Proyecto

![xyz-sdr Architecture](resources/svg/architecture.svg)

```
xyz-sdr/
├── main.py                     # Punto de entrada de la aplicación
├── config/
│   └── defaults.toml           # Configuración inicial por defecto (FFT, sample rate, etc.)
├── core/
│   ├── device.py               # Abstracción e interfaz del hardware SDR (SoapySDR)
│   ├── config_store.py         # Persistencia parcial de ajustes en TOML
│   ├── dsp.py                  # Procesamiento de señal: FFT, filtros, demodulación (FM/AM/SSB)
│   ├── audio_output.py         # Salida de audio demodulado (callback + cola)
│   └── scanner.py              # Escáner espectral automatizado
├── tui/
│   ├── app.py                  # Orquestador del layout y bindings de la TUI Textual
│   └── widgets/
│       ├── __init__.py         # Exports de componentes
│       ├── frequency_timeline.py # Regla y cursor de frecuencia
│       ├── spectrum_graph.py   # Gráfico FFT interactivo
│       └── waterfall_timeline.py # Cascada (waterfall) re-alineada por frecuencia
├── docs/                       # Documentación detallada de desarrollo
│   ├── architecture.md         # Flujo de datos y arquitectura interna
│   ├── bandwidth.md            # Selector de bandwidth IQ, zoom dinámico, persistencia
│   ├── widgets.md              # Documentación técnica de los componentes visuales
│   └── customization.md        # Guía para personalizar estilos, colores y lógica
└── roadmap.md                  # Plan de ruta y fases del proyecto
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
   ```bash
   python main.py --list-dev
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

---

## 📖 Documentación Completa

Para profundizar en el diseño e implementación del proyecto, consulta los documentos de desarrollo en el directorio `/docs`:
- [Arquitectura Interna](docs/architecture.md)
- [Bandwidth IQ (Sample Rate)](docs/bandwidth.md)
- [Banda audible (PASS)](docs/passband.md)
- [Funcionamiento de Widgets](docs/widgets.md)
- [Guía de Modificación y Estilos](docs/customization.md)

### Bandwidth IQ — resumen rápido

1. Usa el desplegable **BANDWIDTH** (o tecla **`B`**) bajo la frecuencia.
2. Elige un preset (250 kHz … 8 MHz según hardware).
3. La app pausa RX, reconfigura el SDR, adapta el zoom y guarda en `config/defaults.toml`.
4. La frecuencia sintonizada y el centro del viewport **no se mueven**.

Presets y lógica interna: [docs/bandwidth.md](docs/bandwidth.md).

---

![xyz-sdr Footer](resources/svg/footer.svg)
