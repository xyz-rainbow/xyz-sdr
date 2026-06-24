# Audio — xyz-sdr

This document covers **demodulated RF audio** (real-time listening) and the **UI sound-effects engine** (clicks, blips, chimes). These are separate audio paths.

---

## Demodulated audio (RX)

When reception is active (`S` / **INICIAR RX**), the RX worker in `tui/app.py`:

1. Reads IQ from `SDRDevice.read_samples()` — SoapySDR on real hardware, `SimulatedSDR` with `--sim`.
2. Demodulates per `demod_mode` (`wbfm`, `nbfm`, `am`, `usb`, `lsb`) via `core/dsp.demodulate()`, using the configured PASS bandwidth and FM de-emphasis (`fm_deemphasis_us`, default **50 µs EU**). For high IQ bandwidth (BANDWIDTH selector), the demodulator **decimates IQ internally** before filtering so audio quality does not degrade at 4–8 MHz capture rates.
3. Applies **FM AGC** (`fm_agc_enabled`, default on) for `wbfm` / `nbfm` — slow attack, fast release to stabilize level between stations.
4. Applies squelch (optional) and enqueues audio through **`AudioOutputQueue.enqueue()`** (`core/audio_output.py`) **without blocking** the RX thread. Output rate follows `dsp.audio_rate` (default 48 kHz). Resampling uses `resample_audio_to_rate()` for exact rational rates.

Per-preset DSP profiles: [`core/dsp_profiles.py`](../core/dsp_profiles.py) — see [audio-presets-research.md](audio-presets-research.md).

`AudioOutputQueue` uses a `sounddevice` `OutputStream` with a callback and a bounded queue (~8 chunks). On saturation it drops the oldest chunk (`put_nowait` + discard). User volume (0–100 %, shortcut `V`) is applied in the callback.

| Mode | IQ source | Notes |
|------|-----------|-------|
| `--sim` | Fixed synthetic stations + noise | UI/demod testing without SDR |
| Real hardware | SoapySDR `readStream` | USB/CPU latency; see [hardware.md](hardware.md) if audio stutters |

Demod normalization uses `NORMALIZE_LEVEL` in `core/dsp.py`; FM AGC and user volume (`V`) shape final loudness.

### FM settings (Esc → **Audio FM / Noise**)

| Setting | TOML key | Default | Notes |
|---------|----------|---------|-------|
| De-emphasis | `fm_deemphasis_us` | `50` | **50 µs** (EU broadcast), **75 µs** (Americas) |
| FM AGC | `fm_agc_enabled` | `true` | Post-demod level tracking for WBFM/NBFM |
| Squelch | `squelch_enabled` | `false` | Mutes audio below SNR threshold |

---

## UI sound-effects engine

The retro UI feedback sounds live in `AudioEffects` (`core/audio_effects.py`).

Unlike traditional media players that load external `.mp3` or `.wav` files, xyz-sdr uses **direct digital synthesis (DDS)**. All effects are generated in memory at app startup.

### Engine characteristics

1. **Non-blocking**: Playback uses `sounddevice` (`sd.play(..., blocking=False)`) so the Textual main thread stays responsive.
2. **Fail-safe**: Wrapped in `try/except`; missing or busy audio hardware fails silently with a debug log only.
3. **Toggle**: Enable/disable globally via **Efectos Sonido** in the settings menu (Esc).

---

## Sound library

Samples are generated at **44100 Hz** as `numpy.float32` arrays.

### 1. Click (tuning / scroll)

- **Design**: Short high-frequency tone (12 ms) with exponential decay.
- **Formula**: $s(t) = \sin(2\pi \cdot 900 \cdot t) \cdot e^{-t / 0.003} \cdot 0.25$
- **Use**: Quick feedback. Disabled during continuous frequency scroll to avoid audio saturation.

### 2. Blip (selection / interaction)

- **Design**: Medium-frequency pulse (650 Hz), 35 ms linear falloff.
- **Formula**: $s(t) = \sin(2\pi \cdot 650 \cdot t) \cdot (1.0 - t/t_{max}) \cdot 0.12$
- **Use**: Buttons (`btn_rx`, `btn_spd_*`), demod mode buttons, `Select` widgets.

### 3. Chime (success / settings applied)

- **Design**: Ascending 4-note arpeggio (C5, E5, G5, C6), 220 ms envelope.
- **Use**: Confirming settings in modal dialogs (Hardware, Noise Removal).

### 4. Error (validation failure)

- **Design**: Dissonant buzz (130 Hz + 260 Hz harmonic), 180 ms.
- **Use**: Invalid frequency input in `inp_freq`.

### 5. Startup

- **Design**: Upward chirp 350 Hz → 1100 Hz over 350 ms with soft attack.
- **Use**: After TUI mount and successful device open.

---

## TUI integration points

Sound triggers in `XyzSDRApp`:

- **`on_mount`**: `play_startup()` after hardware init.
- **`on_button_pressed`**: `play_blip()` for RX toggle and waterfall speed buttons.
- **`on_click`**: `play_blip()` on demod mode buttons.
- **`on_select_changed`**: `play_blip()` on preset/gain changes.
- **`on_input_submitted`**: `play_error()` on invalid frequency input.
