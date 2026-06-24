"""Loop RX desacoplado de la app Textual (ejecutar en hilo worker)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from core.band_buffer import BandFrameMailbox, make_band_frame
from core.dsp import (
    average_psd,
    apply_fm_agc,
    apply_squelch_with_state,
    compute_audio_chunk_samples,
    compute_effective_band_cols,
    compute_effective_fft_size,
    compute_rx_chunk_samples,
    demodulate,
    estimate_snr_at_freq,
)
from core.dsp_profiles import effective_fft_avg, profile_for_sample_rate


class RxWorkerHost(Protocol):
    """Contrato mínimo que la app expone al worker RX."""

    _rx_active: bool
    _bandwidth_changing: bool
    sample_rate: float
    tuned_frequency: float
    visible_span: float
    _display_width: int
    demod_mode: str
    squelch_enabled: bool
    squelch_threshold: float
    passband_center_hz: float
    passband_width_hz: float
    fm_deemphasis_us: float
    fm_agc_enabled: bool
    debug_mode: bool
    config: dict
    _device: Any
    _band_mailbox: BandFrameMailbox
    _recorder: Any
    _audio_output: Any
    _fm_demod_state: Any
    _fm_agc: Any
    _squelch_gate: Any
    _squelch_open: bool
    _debug_lock: Any
    _debug_rx_proc_ms: list
    _debug_rx_iter_count: int
    _debug_chunk_samples: list
    _debug_chunk_duration_ms: list
    _debug_demod_ms: list
    _debug_audio_samples: list


@dataclass
class RxIterationResult:
    """Resultado opcional de una iteración (para tests)."""

    snr: float
    frame_published: bool
    audio_enqueued: bool


def run_rx_iteration(host: RxWorkerHost) -> RxIterationResult | None:
    """Una iteración del loop RX. Devuelve None si debe continuar sin publicar."""
    if host._bandwidth_changing:
        time.sleep(0.01)
        return None

    dsp_cfg = host.config.get("dsp", {})
    base_fft = int(dsp_cfg.get("fft_size", 8192))
    num_avg = int(dsp_cfg.get("fft_avg_windows", 8))
    fft_overlap = float(dsp_cfg.get("fft_overlap", 0.5))
    base_band_cols = int(dsp_cfg.get("band_cache_cols", 1024))

    capture_rate = float(host.sample_rate)
    capture_freq = float(host.tuned_frequency)
    capture_span = float(host.visible_span)
    display_width = max(int(host._display_width), 40)
    fft_size = compute_effective_fft_size(
        base_fft, capture_rate, capture_span, display_width=display_width
    )
    band_cols = compute_effective_band_cols(
        base_band_cols, capture_rate, capture_span, display_width=display_width
    )
    profile = profile_for_sample_rate(capture_rate)
    avg_windows = effective_fft_avg(num_avg, profile)

    spec_samples = compute_rx_chunk_samples(
        fft_size=fft_size,
        sample_rate=capture_rate,
        num_avg=avg_windows,
        chunk_scale=profile.chunk_scale,
        low_rate_scale=profile.chunk_scale if capture_rate < 500_000 else None,
    )
    audio_iq_samples = compute_audio_chunk_samples(
        spec_samples,
        capture_rate,
        audio_chunk_max=profile.audio_chunk_max,
        fft_size=fft_size,
    )
    num_samples = max(spec_samples, audio_iq_samples)

    samples = host._device.read_samples(num_samples)
    if not host._rx_active or host._bandwidth_changing:
        return None

    audio_samples = samples[-audio_iq_samples:] if len(samples) > audio_iq_samples else samples
    proc_t0 = time.perf_counter()
    _, psd = average_psd(
        samples,
        fft_size=fft_size,
        sample_rate=capture_rate,
        num_avg=avg_windows,
        overlap=fft_overlap,
    )
    snr = estimate_snr_at_freq(
        psd,
        capture_freq,
        capture_rate,
        float(host.passband_center_hz),
        passband_width_hz=float(host.passband_width_hz),
    )
    host._squelch_gate.configure(threshold_db=float(host.squelch_threshold))
    frame = make_band_frame(psd, capture_freq, capture_rate, band_cols=band_cols)
    host._band_mailbox.publish(frame, snr)

    if host.debug_mode:
        proc_ms = (time.perf_counter() - proc_t0) * 1000.0
        chunk_duration_ms = (len(samples) / capture_rate) * 1000.0 if capture_rate else 0.0
        with host._debug_lock:
            host._debug_rx_iter_count += 1
            host._debug_rx_proc_ms.append(proc_ms)
            host._debug_chunk_samples.append(len(samples))
            host._debug_chunk_duration_ms.append(chunk_duration_ms)
            if len(host._debug_rx_proc_ms) > 120:
                host._debug_rx_proc_ms.pop(0)
            if len(host._debug_chunk_samples) > 120:
                host._debug_chunk_samples.pop(0)
            if len(host._debug_chunk_duration_ms) > 120:
                host._debug_chunk_duration_ms.pop(0)

    if host._recorder and host._recorder.active and host._recorder.records_iq:
        host._recorder.write_iq(samples)

    audio_enqueued = False
    capture_mode = host.active_demod_mode
    if host._audio_output and capture_mode in ["wbfm", "nbfm", "am", "usb", "lsb", "cw", "dsb", "raw"]:
        audio_rate = int(dsp_cfg.get("audio_rate", 48_000))
        freq_offset = float(host.passband_center_hz) - capture_freq
        demod_t0 = time.perf_counter()
        audio = demodulate(
            audio_samples,
            mode=capture_mode,
            sample_rate=capture_rate,
            audio_rate=audio_rate,
            passband_width_hz=float(host.passband_width_hz),
            fm_deemphasis_us=float(host.fm_deemphasis_us),
            frequency_offset_hz=freq_offset,
            fm_state=host._fm_demod_state,
            profile=profile,
        )
        if capture_mode in ("wbfm", "nbfm"):
            audio = apply_fm_agc(
                audio, host._fm_agc, enabled=bool(host.fm_agc_enabled), sample_rate=audio_rate
            )
        audio, squelch_open = apply_squelch_with_state(
            audio, snr, host._squelch_gate, enabled=bool(host.squelch_enabled)
        )
        host._squelch_open = not host.squelch_enabled or squelch_open
        if host._recorder and host._recorder.active and host._recorder.records_audio:
            host._recorder.write_audio(audio)
        host._audio_output.enqueue(audio)
        audio_enqueued = True
        if host.debug_mode:
            demod_elapsed = (time.perf_counter() - demod_t0) * 1000.0
            with host._debug_lock:
                host._debug_demod_ms.append(demod_elapsed)
                host._debug_audio_samples.append(len(audio))
                if len(host._debug_demod_ms) > 120:
                    host._debug_demod_ms.pop(0)
                if len(host._debug_audio_samples) > 120:
                    host._debug_audio_samples.pop(0)
    elif host.squelch_enabled:
        host._squelch_open = host._squelch_gate.is_open(snr)
    else:
        host._squelch_open = True

    return RxIterationResult(snr=snr, frame_published=True, audio_enqueued=audio_enqueued)
