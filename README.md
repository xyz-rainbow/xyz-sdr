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
  * **Control total con Ratón**: Haz clic en la **timeline de frecuencias** para sintonizar directamente. Clic en espectro o cascada desenfoca los controles sin cambiar la frecuencia. Usa la rueda del ratón (`Scroll`) en timeline, espectro o cascada para desplazarte por la banda, y `Ctrl + Scroll` para zoom in/out.
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
| `G` | Enfocar el selector de ganancia del hardware | — |
| `V` | Enfocar el selector de volumen de salida de audio | — |
| `Esc` | Abrir menú de ajustes (hardware, squelch, efectos) | — |
| `Q` | Cerrar la aplicación de manera segura | — |

---

## 💾 Instalación y Ejecución rápida

**Requisito hardware real:** Python **3.11 o 3.12** (64-bit). PothosSDR incluye bindings embebidos solo para Python 3.9; en 3.13+ no hay wheel `SoapySDR` en pip.

1. **Instalar Drivers SDR (Solo Windows)**:
   ```powershell
   .\setup\install_drivers.ps1
   ```
2. **Instalar Dependencias de Python**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Verificar el Entorno**:
   ```bash
   python setup/check_env.py
   ```
   Debe mostrar `[OK] SoapySDR importado` y tu dispositivo (p. ej. `driver=sdrplay`).
   Si acabas de instalar PothosSDR, **cierra y reabre la terminal** antes de continuar.

4. **Listar hardware detectado**:
   ```bash
   python main.py --list-dev
   ```

5. **Verificación manual (Windows)**:
   ```powershell
   SoapySDRUtil --find=driver=sdrplay
   ```

6. **Ejecutar en modo Simulado (Sin Hardware SDR conectado)**:
   ```bash
   python main.py --sim
   ```

7. **Ejecutar con Hardware SDR**:
   ```bash
   python main.py --driver sdrplay --freq 100.6 --gain 40
   ```
   O deja que elija el primer dispositivo: `python main.py --driver auto`

---

## 📖 Documentación Completa

Para profundizar en el diseño e implementación del proyecto, consulta los documentos de desarrollo en el directorio `/docs`:
- [Arquitectura Interna](docs/architecture.md)
- [Bandwidth IQ (Sample Rate)](docs/bandwidth.md)
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
