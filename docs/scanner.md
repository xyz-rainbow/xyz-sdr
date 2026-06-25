# Escáner de banda — `tui/app.py`

El escáner barre un rango de frecuencias buscando señales activas y, opcionalmente, pausa al detectar una para que puedas escucharla. Está pensado para localizar actividad rápidamente (emisoras FM, canales airband, PMR446…) antes de detenerte a monitorizar.

> **Ubicación del código:** toda la lógica vive en `tui/app.py` (`action_toggle_scan`, `_start_scanning`, `_stop_scanning`, `_pause_scan_on_signal`, `_resume_scanning`, `_step_scanner`, `_handle_scanner_step`). **No existe `core/scanner.py`** — el detector reutiliza el auto-level por columnas del espectro (`floors` / `ceilings` por columna). Ver [Gaps](#gaps-reconocidos).

---

## Resumen

Cuando pulsas **🔍 ESCANEAR BANDA** en la TUI con RX activo, la app:

1. Lee la configuración `[scanner]` (rango, paso, dwell, umbral, histéresis).
2. Sintoniza la frecuencia de inicio y aplica el cambio al SDR (`tuned_frequency = scan_start`).
3. En cada frame RX entrante, mide el **SNR dentro del PASS** (ancho audible actual).
4. Si supera `min_snr_db`:
   * `pause_on_signal = true` → pausa el barrido, suena un chime, la etiqueta del botón pasa a `▶ CONTINUAR ESCANEO`.
   * `pause_on_signal = false` → continúa barriendo, solo loguea una vez por señal.
5. Si está por debajo del umbral, espera `dwell_ms` y avanza `freq_step`. Si supera `freq_end`, vuelve a `freq_start` (bucle continuo).
6. Si está en pausa, vigila: cuando el SNR cae por debajo de `pause_resume_snr_db` durante `dwell_ms` consecutivos, **reanuda automáticamente** el barrido.

**No hay decodificación de señal ni medida de potencia absoluta**: el detector mira el *contraste* entre techo y suelo del passband dentro del espectro ya auto-nivelado por columnas. Eso lo hace robusto frente a ganancia variable pero **frágil frente a señales fuera del passband** (ver [Limitaciones](#limitaciones)).

---

## Activación

| Vía | Detalle |
|-----|---------|
| **Botón lateral `#btn_scan`** | Único punto de entrada. Cambia de etiqueta según el estado: `🔍 ESCANEAR BANDA` (inactivo) → `■ DETENER ESCANEO` (barrido) → `▶ CONTINUAR ESCANEO` (pausado) → clic reanuda. |
| **Teclado** | **Sin binding dedicado** (gap menor). `action_toggle_scan` existe pero no está en `BINDINGS`; se llega solo por el botón. |
| **Pre-requisito** | RX activo (`S` para iniciar). Si no, reproduce sonido de error y loguea `[ERROR] Inicia RX antes de escanear`. El escaneo **no** detiene RX ni el audio. |

Salir del modo escaneo:

* Botón `■ DETENER ESCANEO` → `_stop_scanning()` → estado limpio, sintonía se queda en la última frecuencia visitada.
* Detener RX (`S`) → no detiene el escaneo automáticamente (gap menor: hoy el estado de escaneo sobrevive a un stop/start de RX, pero `_start_scanning()` fallará si vuelves a entrar; ver gaps).
* `Q` (quit) → cierra la app.

---

## Algoritmo

Pseudo-código simplificado (de `_handle_scanner_step()` + `_step_scanner()`):

```python
# Config leída al pulsar el botón
scan_start  = 88 MHz
scan_end    = 108 MHz
scan_step   = 200 kHz
dwell_ms    = 500
min_snr_db  = 10.0
pause_on_signal = True
pause_resume_snr_db = 7.0

# Estado interno
scanning   = True|False
paused     = True|False
pause_below_since = 0.0      # timestamp del primer frame bajo el umbral de reanudar
tuned_at   = time()           # última vez que se cambió la sintonía
last_signal = 0.0             # última vez que se vio SNR >= min_snr_db

# En cada frame RX:
frame_center ≈ tuned_frequency (±10 Hz)
floors, ceilings = auto_level_por_columna(frame)   # vienen del pipeline de display

# 1. Calcular columnas del PASS actual
col_l, col_r = freq_to_col(passband_left, passband_right)
passband_snr = max(ceilings[col_l:col_r+1] - floors[col_l:col_r+1])

# 2. Si estamos en pausa
if paused:
    if passband_snr < pause_resume_snr_db:
        if pause_below_since == 0:
            pause_below_since = now
        elif now - pause_below_since >= dwell_ms / 1000:
            resume_scanning()
    else:
        pause_below_since = 0
    return

# 3. Si NO estamos en pausa
if passband_snr >= min_snr_db:
    if pause_on_signal:
        pause_scan_on_signal(passband_snr)
        return
    log("Señal en {freq} (SNR: {snr} dB)")
    last_signal = now
else:
    ref = last_signal if last_signal > 0 else tuned_at
    if now - ref >= dwell_ms / 1000:
        step_scanner()        # avanza freq_step; vuelve a start si pasa end
```

Características concretas:

* **Paso `freq_step`:** incremento lineal fijo en Hz. Si `freq_step` no divide `(freq_end - freq_start)` exacto, el barrido se redondea al múltiplo siguiente de `freq_step` desde `freq_start` y luego salta a `freq_start` cuando supera `freq_end`. No hay wrap-around ni solapamiento.
* **Dwell (`dwell_ms`):** es el **tiempo mínimo** que se permanece en cada frecuencia sin señal. Cuando hay señal, el dwell se ignora (se decide por SNR, no por tiempo fijo).
* **Umbral (`min_snr_db`):** contraste passband en dB entre techo y suelo de columna. Con `display_level_mode = "per_column"`, las columnas se normalizan individualmente → un valor de 10 dB indica "hay algo claramente por encima del suelo local". En modo `display_level_mode = "global"`, el suelo es compartido y el SNR efectivo cambia (ver [Limitaciones](#limitaciones)).
* **Histéresis (`pause_resume_snr_db`):** siempre debe ser **menor que `min_snr_db`** (recomendado: 3 dB menos). Evita reanudar en valles de modulación y volver a pausar inmediatamente.
* **`pause_on_signal`:** si es `false`, el barrido continúa siempre y solo loguea una vez por señal (no se pausa, no hay chime).
* **Detección de "frecuencia lista":** `_handle_scanner_step` descarta frames cuyo `center_hz` difiere de `tuned_frequency` en más de 10 Hz (espera a que Soapy termine el re-tune).
* **Frecuencias decimales:** se guardan como enteros Hz en TOML; al loguear se imprime en MHz con 4 decimales (`f"{freq/1e6:.4f} MHz"`).

---

## Configuración `[scanner]`

Vive en `config/defaults.toml` bajo `[scanner]`. La UI expone edición en **Esc → Ajustes del Escáner** (`tui/widgets/settings_menu.py`::page_scanner). Tabla ampliada (referencia canónica corta: [configuration.md](configuration.md#scanner--escáner-espectral)):

| Clave | Tipo | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `false` | Reservado. La activación real es vía botón (`action_toggle_scan`); el flag no se consulta en runtime. |
| `freq_start` | int (Hz) | `88_000_000` | Frecuencia de inicio del barrido. UI muestra valor en MHz con 3 decimales. |
| `freq_end` | int (Hz) | `108_000_000` | Frecuencia final. Si `freq_end ≤ freq_start`, el barrido termina inmediatamente (ver gaps). |
| `freq_step` | int (Hz) | `200_000` | Incremento por paso. UI muestra en kHz con 1 decimal. Pasos típicos: 5–25 kHz (airband), 100–200 kHz (FM), 1–10 MHz (espectro amplio). |
| `dwell_ms` | int (ms) | `500` | Tiempo mínimo por frecuencia sin señal y, durante la pausa, tiempo que el SNR debe estar por debajo de `pause_resume_snr_db` antes de reanudar. UI muestra en ms enteros. |
| `min_snr_db` | float (dB) | `10.0` | Umbral alto: SNR passband para considerar "hay señal". UI muestra con 1 decimal. |
| `pause_on_signal` | bool | `true` | Si es `true`, pausa al detectar. Si es `false`, sigue barriendo y solo loguea. |
| `pause_resume_snr_db` | float (dB) | `7.0` | Umbral bajo (histéresis). Cuando SNR cae por debajo durante `dwell_ms`, se reanuda automáticamente. UI muestra con 1 decimal. |

Persistencia: `_persist_scanner_section()` invoca `patch_scanner_section()` en `core/config_store.py` (reescribe solo las claves, preserva comentarios). El botón **Aplicar** de la página del escáner es el que dispara la persistencia.

---

## Salida

### Cuando encuentra señal (`pause_on_signal = true`)

* `_pause_scan_on_signal()`:
  * `_scan_paused = True`, `_scan_pause_below_since = 0`.
  * `audio_effects.play_chime()` — feedback sonoro inmediato.
  * Log: `[SCAN] Pausa — señal {snr:.1f} dB en {freq/1e6:.4f} MHz`.
  * Botón `#btn_scan` cambia a `▶ CONTINUAR ESCANEO` (`variant="warning"`).

### Reanudación automática

* Mientras está en pausa, cada frame comprueba: si `passband_snr < pause_resume_snr_db` durante `dwell_ms` consecutivos → `_resume_scanning()`.
  * `_scan_paused = False`, reinicia timers.
  * Log: `[SCAN] Reanudando escaneo`.
  * Botón vuelve a `■ DETENER ESCANEO` (`variant="error"`).

### Reanudación manual

* Clic en `▶ CONTINUAR ESCANEO` → `action_toggle_scan()` → `_resume_scanning()` (mismo flujo).

### Cuando `pause_on_signal = false`

* El barrido no se detiene nunca por señal. Solo se loguea una vez por frecuencia detectada: `[SCAN] Señal en {freq} MHz (SNR: {snr} dB)`. Esto es útil para *inventariar* una banda: dejas correr 10 minutos y obtienes un log con todas las portadoras activas.

### Step en barrido normal

* Log: `[SCAN] Sintonizando: {next_freq/1e6:.4f} MHz`.
* Llama `self._apply_tuning()` que reconfigura `center_freq` en el SDR.
* Espera a que Soapy confirme el re-tune (`_handle_scanner_step` descarta frames con `|frame.center - tuned| > 10 Hz`).

### Detención

* `■ DETENER ESCANEO` → `_stop_scanning()` → log `[SCAN] Escaneo detenido`, botón vuelve a `🔍 ESCANEAR BANDA` (`variant="primary"`), `_scanning = False`, `_scan_paused = False`. La sintonía queda en la frecuencia actual (no vuelve al `freq_start`).

---

## Limitaciones

1. **Bandas demasiado anchas.** Con `freq_step = 200 kHz` y 20 MHz de rango hay 100 saltos. Cada paso necesita al menos `dwell_ms` (500 ms) + el tiempo de re-tune del SDR (~50–200 ms según driver y filtro) → ~1 minuto por barrido completo. Pasos pequeños en bandas grandes son lentos.
2. **Paso no divisible.** Si `(freq_end - freq_start)` no es múltiplo exacto de `freq_step`, el barrido termina saltando al `freq_start` desde una frecuencia arbitraria (puede saltarse un fragmento del final).
3. **Detección basada en passband.** Si `passband_width_hz` es muy estrecho (p.ej. 5 kHz en NBFM) y `freq_step` es mucho mayor, el escáner puede **saltarse señales que caigan entre dos pasos**. Reduce `freq_step` o amplía el PASS.
4. **Modo `display_level_mode = "global"`.** El suelo es común para todas las columnas → señales fuera del passband (interferentes fuertes en otras frecuencias) pueden *elevar el suelo global* y ocultar la señal real bajo el umbral. Recomendado: `display_level_mode = "per_column"` (default).
5. **Auto-gain del SDR.** Si `auto_gain = true`, el SDR ajusta la ganancia dinámicamente; los `floors` del espectro varían y el umbral `min_snr_db` deja de ser estable. Recomendado: `auto_gain = false` + `gain` fijo.
6. **Señales fuertes fuera de banda.** Interferentes (p.ej. FM broadcast fuerte mientras escaneas airband) pueden saturar el receptor y el SNR aparente cae para todas las frecuencias. Solución: filtro preselector hardware o reducir `gain`.
7. **Sin wrap-around.** El barrido termina al pasar `freq_end` y vuelve a `freq_start`, pero **no avisa al usuario** del wrap. Un log de "barrido completo" no existe (gap).
8. **No aprende.** El escáner no recuerda las frecuencias activas entre sesiones ni construye un inventario persistente. Para eso, redirige el log a un archivo (`--debug` ya loguea en `var/session.log`).
9. **RX obligatorio.** Si RX no está activo, el botón simplemente emite error. No hay `auto_start_rx_on_scan` (gap).
10. **Frecuencias planas (sin modulación).** Una portadora pura sin modulación produce SNR estable, no pausa. Útil para detectarla, pero no indica contenido.

---

## Tubería (pipeline)

```mermaid
flowchart TB
    A[Usuario: clic en<br/>ESCANEAR BANDA] --> B{_rx_active?}
    B -- no --> X1[Sonido error<br/>log: 'Inicia RX antes']
    B -- sí --> C[_start_scanning<br/>lee [scanner] TOML]
    C --> D[tuned_frequency = freq_start<br/>_apply_tuning&#40;&#41;]
    D --> E[Loop: cada frame RX]
    E --> F{_handle_scanner_step}
    F -->|frame.center<br/>!= tuned| E
    F --> G[Calcular passband_snr<br/>max ceil - floor en PASS]
    G --> H{_scan_paused?}
    H -- sí --> I{SNR < resume_snr<br/>durante dwell_ms?}
    I -- sí --> J[_resume_scanning]
    I -- no --> E
    H -- no --> K{SNR >= min_snr?}
    K -- sí + pause_on_signal --> L[_pause_scan_on_signal<br/>chime + log]
    K -- sí + !pause --> M[Log 'Señal']
    K -- no --> N{time - last_step<br/>>= dwell_ms?}
    N -- sí --> O[_step_scanner<br/>tuned += step]
    N -- no --> E
    O -->|next > freq_end| C
    L --> E
    M --> E
    J --> E
```

---

## Ejemplo: sesión típica en airband

Setup (FM broadcast por defecto → airband):

1. Edita `config/defaults.toml`:
   ```toml
   [device]
   driver       = "sdrplay"
   sample_rate  = 250_000      # 250 kHz IQ
   center_freq  = 127_500_000  # centro de la banda airband española
   gain         = 30.0

   [dsp]
   demod_mode      = "nbfm"
   nbfm_bandwidth  = 12_500

   [scanner]
   enabled                  = false
   freq_start               = 118_000_000   # 118 MHz
   freq_end                 = 137_000_000   # 137 MHz
   freq_step                = 25_000        # 25 kHz (canal AM estándar ±)
   dwell_ms                 = 400
   min_snr_db               = 9.0
   pause_on_signal          = true
   pause_resume_snr_db      = 6.0
   ```

2. `.\scripts\run.ps1 -Band airband` → arranca RX en 127.5 MHz nbfm 12.5 kHz.

3. Pulsa el botón **🔍 ESCANEAR BANDA**. Log esperado:
   ```
   [SCAN] Iniciando escaneo (118.00 - 137.00 MHz, paso 25.0 kHz)
   [SCAN] Sintonizando: 118.0000 MHz
   ```
   (760 saltos × ~400 ms ≈ 5 min para un barrido completo, asumiendo dwell exacto sin re-tunes lentos.)

4. La app va saltando. Cuando aterriza en una frecuencia con ATC activo (p.ej. 121.500 MHz emergencia):
   ```
   [SCAN] Pausa — señal 14.2 dB en 121.5000 MHz
   ```
   * Suena chime. Botón cambia a `▶ CONTINUAR ESCANEO`.
   * El audio del demodulador sigue corriendo: oyes la transmisión.
   * Si te interesa, ajustas la frecuencia manualmente o pulsas **Guardar Bookmark** para guardarla.

5. La transmisión termina. Después de ~400 ms sin señal, log:
   ```
   [SCAN] Reanudando escaneo
   [SCAN] Sintonizando: 121.5250 MHz
   ```
   (Continúa desde donde pausó.)

6. Pulsa **■ DETENER ESCANEO** cuando quieras parar. Log:
   ```
   [SCAN] Escaneo detenido
   ```

Cálculo de barrido completo:

* Pasos totales = ⌈(137_000_000 − 118_000_000) / 25_000⌉ = 760.
* Tiempo por paso ≈ `dwell_ms` + re-tune ≈ 400 ms + 80 ms ≈ 480 ms.
* Tiempo total = 760 × 480 ms ≈ **6 minutos** por barrido completo de airband.

Variante "inventario rápido":

```toml
[scanner]
freq_step    = 50_000          # paso más grueso
dwell_ms     = 200
pause_on_signal = false        # no pausa, solo loguea
```

→ 380 pasos × 280 ms ≈ **1.8 minutos** por barrido, con un log tipo:

```
[SCAN] Señal en 121.5000 MHz (SNR: 14.2 dB)
[SCAN] Señal en 125.2500 MHz (SNR: 11.8 dB)
[SCAN] Señal en 130.1000 MHz (SNR: 10.5 dB)
```

---

## Tests relevantes

* `resources/test/test_sdr_features.py::test_patch_recorder_and_scanner_config` — verifica persistencia del `[scanner]`.
* No hay test de la lógica del escáner en sí (gap: la lógica vive en TUI y no se ejercita headless). Considerar refactor a `core/scanner.py` para poder testearlo.

---

## Gaps reconocidos

1. **Sin `core/scanner.py`.** Toda la lógica vive en `tui/app.py` y no es testeable headless. Un refactor futuro debería extraer `Scanner` a `core/` con un callback al TUI.
2. **Sin binding de teclado** dedicado para `action_toggle_scan`. Solo accesible vía botón.
3. **Estado de escaneo sobrevive a stop/start de RX.** Si detienes RX mientras escaneas, `_scanning` sigue `True`. Al pulsar `🔍 ESCANEAR BANDA` después de un `S`/`S`, `_start_scanning()` no se llama porque ya está "scanning" pero `_rx_active` puede ser `False` → el siguiente frame no llega y el escaneo se queda colgado. Workaround: pulsar `■ DETENER ESCANEO` antes de detener RX.
4. **No loguea wrap-around.** Cuando el barrido salta de `freq_end` a `freq_start`, no hay evento visible.
5. **`enabled` no se consulta.** La clave existe en config y UI pero el código no la lee.
6. **`freq_end ≤ freq_start` no validado.** Provoca que el primer step ya supere `freq_end` y salte al inicio en el primer frame.
7. **Sin inventario persistente.** Las señales detectadas solo viven en el log de la sesión; no se guardan en `var/scanner_log.toml` ni similar.
8. **Sin filtrado por tipo de modulación.** El escáner pausa en cualquier SNR alto, incluso si el demodulador actual (p.ej. NBFM) no produce audio audible (p.ej. una portadora CW).

---

## Referencias cruzadas

* [configuration.md](configuration.md#scanner--escáner-espectral) — referencia corta de las claves TOML.
* [dsp.md](dsp.md) — demoduladores cuyo modo debe estar alineado con lo que escaneas.
* [display.md](display.md) — `display_level_mode` afecta a la SNR efectiva.
* [recorder.md](recorder.md) — patrón de detección de SNR que se reutilizará para auto-record.
* `tui/app.py` :: `action_toggle_scan`, `_start_scanning`, `_stop_scanning`, `_pause_scan_on_signal`, `_resume_scanning`, `_step_scanner`, `_handle_scanner_step`.
* `core/config_store.py` :: `patch_scanner_section` — persistencia.
* `tui/widgets/settings_menu.py` :: `page_scanner` — UI de configuración.