# Audio presets research — xyz-sdr

Baseline and design notes for IQ **BANDWIDTH** presets (250 kHz – 8 MHz) on SDRplay RSP1 + xyz-sdr DSP.

---

## Architecture (target)

```
IQ @ SR_capture
  → profile_for_sample_rate()
  → resample_iq_for_demod → SR_demod (per preset)
  → LPF @ PASS/2 (adaptive FIR)
  → demod (FM/AM/SSB) + FmDemodState
  → resample_audio_to_rate → exactly 48_000 Hz
  → de-emphasis (IIR) / AGC / squelch
  → AudioOutputQueue
```

Spectrum path uses the full IQ chunk; audio path uses the **tail** (`audio_samples = samples[-audio_iq_samples:]`) to reduce latency on low presets.

---

## Preset profiles

Implemented in [`core/dsp_profiles.py`](../core/dsp_profiles.py).

| Preset | SR_demod target | min_rate | chunk_scale | fft_avg cap | Recommended modes |
|--------|-----------------|----------|-------------|-------------|-------------------|
| 250 kHz | ≤160 kHz | 80 kHz | 0.25 | 8 | nbfm, am, usb, lsb |
| 500 kHz | ≤250 kHz | 100 kHz | 0.5 | 8 | am, nbfm, usb, lsb |
| 1 MHz | ~560 kHz | 250 kHz | 0.75 | 8 | wbfm, nbfm, am |
| 2.048 MHz | ~560 kHz | 250 kHz | 1.0 | — | wbfm (reference) |
| 4 MHz | ≤768 kHz | 250 kHz | 1.0 | 4 | wbfm, spectrum |
| 8 MHz | ≤768 kHz | 250 kHz | 1.0 | 4 | wbfm, max span |

**WBFM broadcast:** use **1–2 MHz** IQ for best CPU/audio balance. Higher presets improve **spectrum view** only; demod SR is capped at 768 kHz.

---

## External references

| Source | Typical WBFM IQ rate | Notes |
|--------|---------------------|-------|
| SDR++ / SDR# | 1.024–2.4 MHz | FM broadcast demod on decimated IQ |
| GNU Radio `wbfm_rcv` | `quadrature_rate` >> audio_rate | Rational resampler to 48 kHz |
| ITU-R FM | 200 kHz channel | De-emphasis 50 µs (EU) / 75 µs (US) |
| SDRplay RSP1 | Soapy `getSampleRateRange()` | Presets filtered in `SDRDevice.get_supported_sample_rates()` |

---

## Debug metrics (`--debug`)

Log panel reports every ~3 s (with RX active):

- RX iter/s, proc ms, p95
- UI fps, frame latency
- IQ chunk samples + duration ms
- Demod ms, audio samples/iter
- Audio underruns / dropped chunks

---

## Validation

Automated: `resources/test/test_bandwidth_presets.py` — parametrized over all `BANDWIDTH_PRESETS`.

Manual (hardware): see [hardware.md](hardware.md) P0 FM checklist @ 100.6 MHz per preset.

---

## Known limits

- Modos UI `cw`, `dsb`, `raw`, `auto` — sin ruta audio.
- 250 kHz + WBFM: PASS max 250 kHz = Nyquist limit; UI warns on bandwidth change.
- Stereo WBFM / RDS — not implemented (mono discriminator only).
