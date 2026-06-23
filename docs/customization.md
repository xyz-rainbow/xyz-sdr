# 🎨 Guía de Personalización y Modificaciones — xyz-sdr

Esta guía explica cómo modificar la estética, los temas visuales, el comportamiento de sintonía y los algoritmos del software `xyz-sdr`.

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

## 2. Personalizar el Gradiente de Colores del Espectrograma

El espectrograma (cascada) renderiza la fuerza de la señal indexando los valores normalizados en la lista `WATERFALL_GRADIENT` definida en `tui/widgets/waterfall_timeline.py`.

Puedes cambiar completamente el esquema de colores redefiniendo esta lista. Aquí tienes algunas paletas de ejemplo:

### Paleta Térmica Clásica (Actual)
Transita de negro absoluto para ruido débil, pasando por azules, cian, verde, amarillo, naranja y rojo/blanco para picos:
```python
WATERFALL_GRADIENT = [
    "#000000", "#01010b", "#020216", "#040422", "#060630",
    "#080840", "#0a0a52", "#0d0d66", "#10107c", "#111193",
    "#0d36a8", "#0a5dbd", "#0683d1", "#00aeff", "#00c2db",
    "#00d6b0", "#00eb82", "#00ff4c", "#5dfc30", "#a3f915",
    "#e2f600", "#ffff00", "#ffd000", "#ffa000", "#ff6a00",
    "#ff3700", "#ff0000", "#e6004c", "#cc007c", "#d900b3",
    "#ff00ff", "#ffffff"
]
```

### Paleta Monocromática (Fósforo Verde / Militar)
Ideal para emular pantallas de osciloscopio retro:
```python
WATERFALL_GRADIENT = [
    "#000000", "#001100", "#002200", "#004400", "#006600",
    "#008800", "#00aa00", "#00cc00", "#00ee00", "#33ff33",
    "#66ff66", "#99ff99", "#cceecc", "#ffffff"
]
```

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

