# 🔌 Documentación de Widgets Personalizados — xyz-sdr

Este documento detalla el funcionamiento interno de los tres componentes visuales interactivos de la aplicación.

---

## 1. `FrequencyTimeline` (Regla de Frecuencias)

Dibuja una regla horizontal interactiva alineada con el espectro y la cascada.

### Estructura de Renderizado
El método `render()` genera tres filas de texto enriquecido:
1. **Fila 1 (Cursores e Indicador Digital)**:
   * Coloca el cursor sintonizado principal `▼` (rojo) y el cursor de previsualización `▽` (celeste) en sus columnas respectivas.
   * Superpone una lectura digital en alta resolución (ej. `▽ 100.600000 MHz`) en los márgenes de la fila de forma adaptativa.
2. **Fila 2 (Marcas de Ticks)**:
   * Coloca líneas verticales `│` coloreadas en las frecuencias calculadas como "ticks" o en la posición del cursor de sintonía. El resto se completa con líneas de unión horizontales `─`.
3. **Fila 3 (Etiquetas Numéricas)**:
   * Renderiza el valor numérico en MHz (ej. `100.6M`) centrado bajo su marca correspondiente.

### Matemáticas de Ticks (`_nice_tick_spacing`)
Para evitar que las marcas numéricas se solapen o queden demasiado dispersas al variar el zoom (span), el widget calcula dinámicamente un paso de marcas legible utilizando múltiplos de 1, 2, 5 o 10:
$$\text{Spacing} = \text{nice\_step} \times 10^{\lfloor \log_{10}(\text{raw\_spacing}) \rfloor}$$
Donde `nice_step` se ajusta a `[1.0, 2.0, 5.0, 10.0]` según la escala visual óptima.

---

## 2. `SpectrumGraph` (Analizador Espectral FFT)

Muestra los picos de potencia de la señal en tiempo real mediante barras verticales de caracteres ASCII (`▁▂▃▄▅▆▇█`).

### Algoritmo de Agregación de Picos (Máxima Resolución)
Al renderizar spans muy anchos de frecuencia en una terminal con pocas columnas (ej. 120 caracteres para 2 MHz), múltiples bins de la FFT (que tiene 4096 bins de resolución) caen dentro del rango representado por un único carácter de pantalla. 
En lugar de tomar una muestra puntual (que causa aliasing y pérdida de señales), el widget calcula el rango exacto de la columna y obtiene el **valor máximo de potencia**:
```python
f_start = left_hz + col * hz_per_col
f_end = left_hz + (col + 1) * hz_per_col
idx_start = np.searchsorted(self._freqs_abs_hz, f_start)
idx_end = np.searchsorted(self._freqs_abs_hz, f_end)

if idx_start < idx_end:
    col_values[col] = np.max(self._psd[idx_start:idx_end])
```
Esto asegura que las portadoras portadoras y transmisiones estrechas (como CW o NBFM) siempre se dibujen a su altura máxima en el gráfico.

---

## 3. `WaterfallTimeline` (Espectrograma en Cascada)

Muestra la actividad del espectro a lo largo del tiempo, desplazando las filas de arriba a abajo.

### Alineación Dinámica Histórica
A diferencia de los waterfalls clásicos que asumen una frecuencia fija, `WaterfallTimeline` admite que el usuario cambie el zoom y el centro del viewport en cualquier momento.
Cada línea guardada en la historia se encapsula en un objeto `_WaterfallRow` que contiene la frecuencia central de captura exacta (`center_hz`), la tasa de muestreo (`sample_rate`) y los datos de potencia (`psd`):
```python
row_left_hz = row.center_hz - row.sample_rate / 2
row_right_hz = row.center_hz + row.sample_rate / 2
```
Al renderizar cualquier columna `col` en la pantalla:
1. Calculamos su frecuencia física absoluta: $f = f_{start} + col \times f_{per\_col}$.
2. Si $f$ está dentro de `[row_left_hz, row_right_hz]`, mapeamos e interpolamos la señal de esa captura histórica mediante agregación de picos (`np.max`) en el segmento correspondiente.
3. Si $f$ está fuera del rango del hardware capturado en esa fila, pintamos el carácter de inactividad `░` con un fondo de color de inactividad `#08080f`.

Esto crea un efecto de **re-alineamiento físico dinámico**: si sintonizas a otra frecuencia o cambias el zoom, la historia visible de la cascada se deforma, escala y desplaza coherentemente en pantalla en lugar de borrarse o desplazarse de forma errática.

---

## 🖱️ Interactividad de Ratón Común
Los tres widgets heredan los siguientes controladores de eventos para unificar la interacción:
* **`on_mouse_scroll_up` / `on_mouse_scroll_down`**:
  * Desplazamiento normal: Envía un mensaje `ScrollRequest` para cambiar la frecuencia hacia arriba o hacia abajo.
  * `Ctrl + Rueda`: Envía un mensaje `ZoomRequest` para acercar/alejar la vista (zoom).
* **`on_mouse_down`**:
  * Calcula la frecuencia física bajo la columna del ratón:
    $$f_{clic} = f_{start} + \left( \frac{x_{mouse}}{\text{width}} \right) \times \text{span}$$
  * Publica un mensaje `TuneRequest` para re-sintonizar el receptor inmediatamente a ese punto.
