# Audio presets — implementation reference

Per-preset DSP targets, validation, and operational guidance for **BANDWIDTH** presets (250 kHz – 8 MHz).

Index: [README.md](README.md) | [dsp.md](dsp.md) | [bandwidth.md](bandwidth.md) | [hardware.md](hardware.md)

---

## Design goal

All six IQ presets must deliver **equivalent FM audio quality** when PASS and de-emphasis are equal — higher presets widen spectrum view without injecting wideband noise into the demod chain.

---

## Target signal chain

```
IQ @ SR_capture
  → profile_for_sample_rate()
  → resample_iq_for_demod → SR_demod (capped per preset)
  → shift_to_baseband + LPF @ PASS/2
  → demod + FmDemodState
  → resample_audio_to_rate → 48_000 Hz exact
  → de-emphasis (IIR) / AGC / squelch
  → AudioOutputQueue
```

---

## Preset profiles (implemented)

Source: `core/dsp_profiles.py`

| Preset | SR_demod max | min_rate | oversample | chunk_scale | fft_avg cap | audio_chunk_max |
|--------|--------------|----------|------------|-------------|-------------|-----------------|
| 250 kHz | 160 kHz | 80 kHz | 2.5 | 0.25 | 8 | 8192 |
| 500 kHz | 250 kHz | 100 kHz | 2.5 | 0.5 | 8 | 16384 |
| 1 MHz | 560 kHz | 250 kHz | 2.8 | 0.75 | 8 | 32768 |
| 2.048 MHz | 560 kHz | 250 kHz | 2.8 | 1.0 | — | 65536 |
| 4 MHz | 768 kHz | 250 kHz | 2.8 | 1.0 | 4 | 65536 |
| 8 MHz | 768 kHz | 250 kHz | 2.8 | 1.0 | 4 | 65536 |

---

## Recommended use

| Preset | Primary use | FM broadcast |
|--------|-------------|--------------|
| 250 kHz | NBFM, AM narrow, SSB | Not recommended (PASS max = Nyquist) |
| 500 kHz | AM, voice | Marginal WBFM |
| **1 MHz** | **Daily WBFM** | Recommended |
| 2.048 MHz | WBFM reference / design default | Excellent |
| 4 / 8 MHz | Wide spectrum scouting | Audio ≈ 1–2 MHz (internal decimation) |

---

## External references

| Source | WBFM IQ rate | Notes |
|--------|--------------|-------|
| SDR++ / SDR# | 1.024–2.4 MHz | FM demod on decimated stream |
| GNU Radio `wbfm_rcv` | `quadrature_rate` >> audio | Rational resampler |
| ITU-R FM | 200 kHz channel | De-emphasis 50/75 µs |
| SDRplay RSP1 | Soapy range | Filtered in `get_supported_sample_rates()` |

---

## Debug instrumentation

Launch with `--debug`. Log fields (see [audio.md](audio.md)):

- `iq N smp`, duration ms
- `demod Xms`
- `audio N smp/iter`
- `audio u/d` — underruns / dropped chunks

Healthy setup: `u/d` near `0/0` at 1–2 MHz WBFM.

---

## Automated validation

```powershell
python -m pytest resources/test/test_bandwidth_presets.py -q
python -m pytest resources/test -q
```

Golden test: WBFM RMS at 2.048 MHz vs 8 MHz within ~9 dB on synthetic FM (regression guard).

---

## Manual QA matrix

| BANDWIDTH | Mode | PASS | Pass criteria |
|-----------|------|------|---------------|
| 250 kHz | nbfm | 12.5 kHz | Low latency, clean narrow audio |
| 500 kHz | am | 10 kHz | Intelligible voice |
| 1 MHz | wbfm | 200 kHz | Reference FM quality |
| 2.048 MHz | wbfm | 200 kHz | Same as 1 MHz |
| 4 / 8 MHz | wbfm | 200 kHz | Audio matches 1–2 MHz; wider spectrum |

Full hardware checklist: [hardware.md](hardware.md) (P0 @ 100.6 MHz).

---

## Known limits

- Mono WBFM only (no stereo pilot decode)
- UI modes `cw`, `dsb`, `raw`, `auto` — no audio path
- 250 kHz + WBFM — Nyquist constraint on 250 kHz PASS max

---

## Implementation history

| Change | Module |
|--------|--------|
| IQ decimation before demod | `resample_iq_for_demod()` |
| Exact 48 kHz output | `resample_audio_to_rate()` |
| Preset profiles | `core/dsp_profiles.py` |
| Spectrum/audio decouple | `compute_audio_chunk_samples()` |
| FM chunk continuity | `FmDemodState` |
| SSB PASS support | `demod_ssb()` |
| Fixed de-emphasis (was no-op) | IIR `fm_deemphasis()` |
| SDRplay plugin false positive fix | `check_sdrplay_plugin()` |
