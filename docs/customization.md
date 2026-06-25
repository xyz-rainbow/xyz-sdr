# 🎨 Guía de Personalización y Modificaciones — xyz-sdr

Esta guía explica cómo modificar la estética, los temas visuales, el comportamiento de sintonía y los algoritmos del software `xyz-sdr`.

Referencia TOML completa: [configuration.md](configuration.md) | Índice: [README.md](README.md)

---

## 1. Modificar Estilos y Temas (CSS/TCSS)

Textual utiliza un sistema de hojas de estilo similar a CSS. Los estilos globales de la aplicación están declarados en la constante `CSS` dentro de `XyzSDRApp` en `tui/app.py`. Los estilos propios de los widgets individuales se declaran en la propiedad `DEFAULT_CSS` de sus clases.

### Cambiar Bordes y Layouts
Para cambiar la apariencia de las cajas de visualización, puedes modificar la regla `border` en el CSS de `app.py`:
```css
/* Para bordes rectos finos */
border: solid #10b981;

/* Para bordes redondeados (por defecto) */
border: round #10b981;

/* Para bordes gruesos de doble línea */
border: double #10b981;
```

---

## 2. Personalizar el Gradiente de Colores (espectro + cascada)

Espectro y waterfall comparten **`THERMAL_GRADIENT`** en `tui/widgets/display_palette.py`. Ambos widgets normalizan con `normalize_per_column()` y colorean con `gradient_color()` / `cell_background()`.

Ver [display.md](display.md) para auto-level y [configuration.md](configuration.md) para claves `[display]`.

Puedes redefinir la tupla `THERMAL_GRADIENT` (32 paradas recomendadas). Ejemplo — paleta térmica actual:
```python
THERMAL_GRADIENT = (
    "#000000", "#01010b", "#020216", "#040422", "#060630",
    # … ver display_palette.py para la lista completa …
    "#ff00ff", "#ffffff",
)
```

### Paleta Monocromática (Fósforo Verde / Militar)
```python
THERMAL_GRADIENT = (
    "#000000", "#001100", "#002200", "#004400", "#006600",
    "#008800", "#00aa00", "#00cc00", "#00ee00", "#33ff33",
    "#66ff66", "#99ff99", "#cceecc", "#ffffff",
)
```

> **Nota:** Ya no uses `WATERFALL_GRADIENT` en `waterfall_timeline.py` (obsoleto); un solo gradiente mantiene colores alineados entre espectro y cascada.

---

## 3. Modificar Pasos de Sintonía y Niveles de Zoom

Las escalas y constantes de sintonía están definidas en la parte superior de `tui/app.py`:

### Configurar Pasos de Desplazamiento (`SCROLL_STEPS`)
Define la lista de pasos que se seleccionan con las teclas `↑` / `↓`. Puedes añadir o remover pasos:
```python
SCROLL_STEPS = [
    1_000,       # 1 kHz
    5_000,       # 5 kHz
    10_000,      # 10 kHz
    25_000,      # 25 kHz
    50_000,      # 50 kHz
    100_000,     # 100 kHz (Estaciones comerciales FM)
    500_000,     # 500 kHz
    1_000_000,   # 1 MHz
    5_000_000,   # 5 MHz
]
```

### Configurar Límites de Zoom (`VISIBLE_SPANS`)
Define el ancho de banda visible (span) en pantalla. Para la v1 del hardware, el span máximo recomendado está limitado por la tasa de muestreo física de captura (2.048 MHz para SDRplay):
```python
VISIBLE_SPANS = [
    50_000,      # 50 kHz (Zoom máximo)
    100_000,     # 100 kHz
    200_000,     # 200 kHz
    500_000,     # 500 kHz
    1_000_000,   # 1 MHz
    2_048_000,   # 2.048 MHz (Ancho de banda completo del hardware)
]
```

---

## 4. Agregar Nuevos Presets de Radio

Los presets mostrados en la lista desplegable izquierda se configuran en la constante `PRESETS` en `tui/app.py`:
```python
PRESETS = [
    # (Nombre en pantalla, Frecuencia en Hz, Modo de demodulación)
    ("RNE Radio Nacional",     100_600_000, "wbfm"),
    ("Aviacion Barcelona APP", 120_900_000, "nbfm"),
    ("PMR Canal 1",            446_006_250, "nbfm"),
    # Añade tus frecuencias preferidas aquí...
]
```
Cuando un usuario selecciona uno de estos presets en la interfaz, la aplicación actualiza automáticamente la sintonía física del dispositivo, centra el viewport y cambia el demodulador a la configuración correspondiente.

---

## 5. Normas de Diseño de la TUI (Actuales y Futuras)

Para mantener la cohesión visual y garantizar una experiencia de usuario consistente a largo plazo, todas las modificaciones de la interfaz deben seguir estas directrices:

### Consistencia en Menús Modales (ESC Settings)
1. **Jerarquía Modular**: El menú de Ajustes (`SettingsScreen`) debe organizarse en base a páginas internas reactivas (`current_page`), con un menú principal de categorías generales que derivan a subpáginas específicas de formularios (ej. `page_hardware`, `page_noise`). Esto previene el desorden visual y simplifica la expansión de opciones futuras.
2. **Ubicación de Botones de Salida**: Todos los menús y submenús modales deben posicionar sus botones de navegación/cierre exactamente en el mismo lugar:
   * **Abajo a la derecha** (`align: right middle;` dentro de la clase `.settings-actions`).
   * El botón de salida (`Cerrar` o `Atrás`) debe ser el primer botón a la izquierda de la sección de acciones, seguido a su derecha por el botón de acción positiva (`Aplicar` o `Guardar`), si corresponde.
   * Esto asegura que el usuario pueda salir del menú o de cualquier subnivel presionando el mismo punto físico o usando la navegación de teclado uniforme.

### Alineación de Controles en Formulario
1. **Distribución Horizontal Compacta**: Al agrupar un interruptor de encendido/apagado y su selector de valor de control (ej. el switch de Squelch y su dropdown de umbral en dB), los controles deben presentarse en paralelo usando un contenedor con `layout: horizontal; height: 3; align: left middle;`. Esto previene el desperdicio de espacio vertical en terminales de baja resolución.
2. **Fondo de Campos de Texto**: Los campos de entrada de texto interactivos (como el campo de frecuencia de sintonía en el menú de controles) deben usar fondo negro (`background: #000000;`) tanto en su estado de reposo como enfocado (`:focus`). El contorno o borde del input se utiliza para representar el foco visual (ej. `border: round #818cf8;`).
3. **Ancho Proporcional**: Los controles desplegables (Select) para valores cortos (como Ganancia o Squelch) deben restringir su ancho (`width`) para evitar que ocupen el 100% de la barra lateral, dejando el ancho completo únicamente para listas largas como presets o nombres de dispositivos.

### Soft corners sin orejas (Outline — sin tint)
Textual dibuja `border: round` sobre un rectángulo. **`background-tint` y fondos sólidos vivos sangran** en las esquinas (no se recortan al radio del borde).

**Patrón obligatorio** con `border: round`:
```css
/* Sidebar → background: #0b0f19 (PANEL_BG) */
/* Espectro/cascada/velocidad → background: #090d16 (DISPLAY_BG) */

MiWidget {
    background: #090d16;           /* = fondo del padre inmediato */
    border: round #4338ca;
    color: #a5b4fc;
}
MiWidget:hover {
    border: round #6366f1;
    color: #e0e7ff;                /* solo borde + texto; sin tint */
}
MiWidget.activo {
    background: #090d16;
    border: round #10b981;
    color: #ffffff;                /* fallback activo: texto lima #a3e635 */
}
```

**No hacer:** `background-tint`, `background: #10b981`, ni `#1e1b4b` en widgets con `border: round`.

### Barra de velocidad de cascada (Fase 1)
- Ancho `3` columnas (~¼ del ancho anterior).
- Fondo botón = `DISPLAY_BG` (`#090d16`).
- Activo (plan B): borde verde + texto lima `#a3e635`, sin relleno.
- Línea separadora: `border-left: solid #1e293b` en `#waterfall_speed_bar`.
- Sin hover visual en controles sidebar (frecuencia, select, RX/Grabar).

---

## 6. Bandwidth IQ (Sample Rate)

El **bandwidth de captura** equivale al `sample_rate` del SDR (`device.sample_rate` en TOML).

### Comportamiento al cambiar bandwidth
1. Se detiene RX de forma segura (worker sincronizado con `_rx_stop_event`).
2. Se aplica el nuevo rate en hardware vía `SDRDevice.set_sample_rate()`.
3. **No se modifican** `tuned_frequency` ni `viewport_center`.
4. El zoom visible se **adapta**: si el span actual excede el nuevo máximo, se hace clamp al zoom-out sin mover el centro.
5. Se reanuda RX si estaba activo.
6. Se persiste en `config/defaults.toml` (`sample_rate`, `center_freq`, `gain`).

### Presets y zoom dinámico
- Presets en `core/device.py` → `BANDWIDTH_PRESETS` (250k … 8M), filtrados por hardware.
- Niveles de zoom en `tui/app.py` → `build_visible_spans(sample_rate)` (100k … sample_rate).

### Cambio de driver (Esc → Hardware)
- Si el hardware no está disponible (p. ej. SDRplay sin SoapySDR), la app **no debe crashear**: revierte al driver anterior y muestra error en el log.
- `change_device_driver()` devuelve `bool`; la UI de ajustes re-sincroniza el Select.

### Atajo
- Tecla **`B`**: enfoca `#sel_bandwidth` (mismo patrón que `G`/`V` para gain/volumen).

Documentación completa: [bandwidth.md](bandwidth.md), [dsp.md](dsp.md).

---

## 7. Ajuste DSP y calidad de audio

Parámetros en `config/defaults.toml` → sección `[dsp]`. Ver [dsp.md](dsp.md).

### Rendimiento vs calidad espectral

Si hay lag o audio entrecortado en hardware real:

```toml
[dsp]
fft_size = 4096          # default ver configuration.md §[dsp]
band_cache_cols = 512    # default ver configuration.md §[dsp]
fft_avg_windows = 4      # default ver configuration.md §[dsp]
display_fps = 15         # default ver configuration.md §[dsp]
```

> Los valores por defecto canónicos (incluidos `fft_size`, `band_cache_cols`, `fft_avg_windows`, `display_fps`) están en [`configuration.md`](configuration.md) §`[dsp]`. Los ejemplos anteriores usan la mitad del valor canónico como punto de partida para reducir carga.

### Audio FM

```toml
[dsp]
fm_deemphasis_us = 50    # 50 EU / 75 US
fm_agc_enabled = true
audio_rate = 48_000
wbfm_bandwidth = 200_000 # PASS audible WBFM (default: ver configuration.md §[dsp])
```

UI alternativa: **Esc → Audio FM / Noise**.

### Preset IQ recomendado

| Uso | `device.sample_rate` |
|-----|----------------------|
| FM broadcast diario | 1_000_000 – 2_048_000 |
| NBFM / AM estrecho | 250_000 – 500_000 |
| Exploración espectro | 4_000_000 – 8_000_000 |

Perfiles automáticos: `core/dsp_profiles.py` — [audio-presets-research.md](audio-presets-research.md).

### Perfiles DSP (avanzado)

Para modificar comportamiento por preset, edita `_PRESET_TABLE` en `core/dsp_profiles.py`:

- `iq_demod_max_hz` — techo SR antes de demod
- `chunk_scale` — tamaño lectura IQ (latencia)
- `fft_avg_cap` — límite promediado FFT en SR altos

Tras cambios, ejecuta: `python -m pytest resources/test/test_bandwidth_presets.py -q`

