"""Tests de core/band_buffer.py — proyección, slice y mailbox coalesced."""

from __future__ import annotations

import threading
import time

import numpy as np

from core.band_buffer import (
    BandFrame,
    BandFrameMailbox,
    make_band_frame,
    project_psd_to_band,
    slice_band_history_to_viewport,
    slice_band_to_viewport,
)


def test_project_psd_to_band_shape(synthetic_psd, center_hz, sample_rate):
    band = project_psd_to_band(synthetic_psd, center_hz, sample_rate, band_cols=512)
    assert band.shape == (512,)
    assert band.dtype == np.float32
    assert np.isfinite(band).any()


def test_slice_band_to_viewport_full_bandwidth(flat_band_cols, center_hz, sample_rate):
    cols = slice_band_to_viewport(
        flat_band_cols,
        center_hz,
        sample_rate,
        center_hz,
        sample_rate,
        terminal_width=80,
    )
    assert cols.shape == (80,)
    assert np.all(np.isfinite(cols))


def test_slice_band_to_viewport_zoom_narrower(flat_band_cols, center_hz, sample_rate):
    full = slice_band_to_viewport(
        flat_band_cols, center_hz, sample_rate, center_hz, sample_rate, 80
    )
    zoom = slice_band_to_viewport(
        flat_band_cols, center_hz, sample_rate, center_hz, 50_000, 80
    )
    assert zoom.shape == (80,)
    assert np.all(np.isfinite(zoom))
    assert not np.allclose(full, zoom, equal_nan=True)


def test_slice_history_matches_row_by_row(flat_band_cols, center_hz, sample_rate):
    rows = [(center_hz, sample_rate, flat_band_cols) for _ in range(12)]
    batch = slice_band_history_to_viewport(rows, center_hz, 100_000, 64)
    assert batch is not None
    assert batch.shape == (12, 64)

    for idx, row in enumerate(rows):
        single = slice_band_to_viewport(row[2], row[0], row[1], center_hz, 100_000, 64)
        np.testing.assert_allclose(batch[idx], single, equal_nan=True)


def test_slice_history_empty_returns_none():
    assert slice_band_history_to_viewport([], 100e6, 100e3, 40) is None


def test_make_band_frame_fields(synthetic_psd, center_hz, sample_rate):
    frame = make_band_frame(synthetic_psd, center_hz, sample_rate, band_cols=256)
    assert isinstance(frame, BandFrame)
    assert frame.center_hz == center_hz
    assert frame.sample_rate == sample_rate
    assert frame.band_cols.shape == (256,)
    assert frame.timestamp <= time.time()


def test_mailbox_coalesces_to_latest_frame(center_hz, sample_rate, flat_band_cols):
    mailbox = BandFrameMailbox()
    f1 = BandFrame(center_hz, sample_rate, 1.0, flat_band_cols)
    f2 = BandFrame(center_hz, sample_rate, 2.0, flat_band_cols + 1.0)

    mailbox.publish(f1, snr=5.0)
    mailbox.publish(f2, snr=9.0)

    frame, snr, seq = mailbox.consume_if_new(0)
    assert frame is f2
    assert snr == 9.0
    assert seq == 2

    frame2, _, seq2 = mailbox.consume_if_new(seq)
    assert frame2 is None
    assert seq2 == seq


def test_mailbox_clear_resets_sequence(center_hz, sample_rate, flat_band_cols):
    mailbox = BandFrameMailbox()
    frame = BandFrame(center_hz, sample_rate, 1.0, flat_band_cols)
    mailbox.publish(frame, 1.0)
    _, _, seq = mailbox.consume_if_new(0)
    mailbox.clear()
    consumed, _, seq_after = mailbox.consume_if_new(seq)
    assert consumed is None
    assert seq_after == seq


def test_mailbox_thread_safe_publish(flat_band_cols, center_hz, sample_rate):
    mailbox = BandFrameMailbox()
    errors: list[Exception] = []

    def worker(n: int) -> None:
        try:
            for i in range(50):
                frame = BandFrame(center_hz, sample_rate, float(i), flat_band_cols)
                mailbox.publish(frame, float(i))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    frame, snr, seq = mailbox.consume_if_new(0)
    assert frame is not None
    assert seq > 0
