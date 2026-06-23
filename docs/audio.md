# 🔊 Motor y Biblioteca de Sonidos — xyz-sdr

Este documento describe el funcionamiento técnico del motor de efectos de sonido, cómo se generan las ondas electromecánicas retro y cómo se integra con la interfaz en terminal (TUI).

---

## 🛠️ Cómo Funciona el Motor de Sonidos

El motor de sonidos está implementado en la clase `AudioEffects` dentro del archivo [audio_effects.py](file:///Y:/[Proyectos]/[General]/[Main]/xyz-sdr/core/audio_effects.py).

A diferencia de los reproductores multimedia tradicionales que cargan archivos `.mp3` o `.wav` externos, `xyz-sdr` utiliza un **motor de síntesis digital directa (DDS)**. Todos los efectos se generan matemáticamente en memoria en tiempo de inicialización de la app.

### Características del Motor:
1. **No Bloqueante**: La reproducción utiliza la biblioteca `sounddevice` (`sd.play(..., blocking=False)`), lo que permite que la interfaz de la terminal responda instantáneamente sin pausar el hilo principal ni retrasar el renderizado de la pantalla.
2. **Fallas Silenciosas (Fail-Safe)**: Todo el sistema de reproducción de audio está envuelto en bloques `try/except`. Si el hardware de sonido del host está ocupado, no tiene controladores instalados, o se ejecuta en un contenedor sin audio, el motor descarta el sonido de manera silenciosa escribiendo únicamente un registro de depuración en los logs de la app. Esto asegura que la aplicación TUI nunca se detenga o falle por problemas de audio del sistema.
3. **Control Dinámico**: Se puede habilitar o deshabilitar globalmente mediante el interruptor **Efectos Sonido** del menú de ajustes (ESC).

---

## 🎵 Biblioteca de Sonidos Utilizados

Las señales de audio se generan usando un muestreo de **44100 Hz** y se exportan como arrays de tipo `numpy.float32`.

### 1. Click (Sintonía / Scroll)
*   **Diseño**: Un tono de alta frecuencia muy corto (12 ms) que decae de forma exponencial.
*   **Fórmula**: $s(t) = \sin(2\pi \cdot 900 \cdot t) \cdot e^{-t / 0.003} \cdot 0.25$
*   **Uso**: Comportamiento de feedback rápido. *Nota: Se ha desactivado intencionadamente en el scroll continuo de frecuencias para evitar saturación del canal de audio durante barridos rápidos.*

### 2. Blip (Selección e Interacción)
*   **Diseño**: Un pulso de frecuencia media (650 Hz) con una caída lineal linealizada (35 ms).
*   **Fórmula**: $s(t) = \sin(2\pi \cdot 650 \cdot t) \cdot (1.0 - t/t_{max}) \cdot 0.12$
*   **Uso**: Interacción con botones (`btn_rx`, `btn_spd_*`), selección de modos de demodulación (`btn_mode_*`) y cambios en menús desplegables (`Select`).

### 3. Chime (Éxito / Ajustes Aplicados)
*   **Diseño**: Un arpegio ascendente de 4 notas en acordes mayores de Do (C5, E5, G5, C6) con una envolvente lineal de atenuación de 220 ms.
*   **Notas**: C5 (523 Hz) ➔ E5 (659 Hz) ➔ G5 (784 Hz) ➔ C6 (1046 Hz).
*   **Uso**: Se reproduce al confirmar y guardar la configuración en las ventanas modales de ajustes (Hardware, Noise Removal).

### 4. Error (Alerta / Validación Fallida)
*   **Diseño**: Un zumbido disonante y áspero (180 ms) que suma la frecuencia fundamental (130 Hz) y su segundo armónico (260 Hz), con una atenuación de ganancia suave.
*   **Fórmula**: $s(t) = (\sin(2\pi \cdot 130 \cdot t) + 0.4 \cdot \sin(2\pi \cdot 260 \cdot t)) \cdot \text{env}(t) \cdot 0.35$
*   **Uso**: Se dispara cuando el usuario ingresa un dato erróneo (como una frecuencia no numérica o fuera de límites en el campo de texto de frecuencia).

### 5. Startup (Inicio de la Aplicación)
*   **Diseño**: Un barrido de frecuencia de subida (*frequency sweep / chirp*) de 350 ms que sube linealmente de 350 Hz a 1100 Hz, con una envolvente de ataque suavizada al inicio para evitar clics abruptos en los altavoces.
*   **Uso**: Se reproduce al terminar de montar la aplicación TUI e iniciar correctamente el flujo del hardware SDR.

---

## 🎛️ Puntos de Integración en la Interfaz (TUI)

Los disparadores de sonido se configuran en los siguientes métodos de la clase principal `XyzSDRApp`:

*   **`on_mount`**: Llama a `self.audio_effects.play_startup()` una vez inicializado con éxito el hardware y montada la interfaz.
*   **`on_button_pressed`**: 
    *   Reproduce `self.audio_effects.play_blip()` al iniciar/detener la recepción (`btn_rx`) o cambiar los FPS del waterfall (`btn_spd_*`).
*   **`on_click`**: 
    *   Reproduce `self.audio_effects.play_blip()` cuando se hace clic en los botones de modo de demodulación (`btn_mode_*`).
*   **`on_select_changed`**: 
    *   Reproduce `self.audio_effects.play_blip()` cuando el usuario selecciona un nuevo preset o ajusta la ganancia.
*   **`on_input_submitted`**:
    *   En caso de capturar un `ValueError` (entrada incorrecta en `inp_freq`), dispara `self.audio_effects.play_error()`. En caso de éxito, no reproduce ningún sonido de sintonía para mantener el entorno silencioso según las especificaciones de diseño.
