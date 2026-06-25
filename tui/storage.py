"""
xyz-sdr | tui/storage.py
StorageController — coordina grabación, bookmarks y persistencia de config.

Antes: ~280 LOC de storage logic vivían en tui/app.py mezcladas con widgets.
Ahora: ``StorageController`` opera contra un ``StorageHost`` (Protocol) que
XyzSDRApp implementa delegando a sus propiedades y métodos existentes.

Equivale a la unión de:
- action_record / _start_recording / _stop_recording
- _load_bookmarks / _action_save_bookmark / export_bookmarks / import_bookmarks
- _persist_device_config / _persist_dsp_config / _persist_recorder_config
  / _persist_scanner_config / _persist_display_config (5 métodos unificados
  en uno solo: ``persist_config(section, **updates)``)

Refs:
- .mavis/plans/deliverables/final_report.md §Fase 3 item 43 (god class refactor)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from core.bookmarks import (
    Bookmark,
    export_bookmarks,
    import_bookmarks,
    load_bookmarks,
    merge_bookmarks,
    save_bookmarks,
)
from core.config_store import (
    patch_app_section,
    patch_device_section,
    patch_display_section,
    patch_dsp_section,
    patch_recorder_section,
    patch_scanner_section,
)
from core.recorder import (
    SDRRecorder,
    recording_targets,
    resolve_recordings_dir,
)

logger = logging.getLogger(__name__)


# ── Host interface ────────────────────────────────────────────────────────────


class StorageHost(Protocol):
    """Interfaz que XyzSDRApp implementa para que StorageController pueda operar.

    Mantenida minimal: solo lo que storage necesita. XyzSDRApp delega a sus
    propiedades y métodos existentes.
    """

    # Properties — read-only state from app
    @property
    def config_path(self) -> str: ...
    @property
    def config(self) -> dict: ...
    @property
    def tuned_frequency(self) -> float: ...
    @property
    def demod_mode(self) -> str: ...
    @property
    def rx_active(self) -> bool: ...
    @property
    def sample_rate(self) -> float: ...
    @property
    def active_demod_mode(self) -> str: ...
    @property
    def project_root(self) -> Path: ...

    # Callbacks
    def log(self, message: str) -> None: ...
    def update_status(self) -> None: ...
    def refresh_preset_select(self) -> None: ...


class AudioEffectsLike(Protocol):
    """Subset de AudioEffects que storage necesita (play_blip/chime/error)."""

    def play_blip(self) -> None: ...
    def play_chime(self) -> None: ...
    def play_error(self) -> None: ...


# ── Result types ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RecordingResult:
    """Resultado de stop_recording: paths a los archivos producidos."""

    iq_path: Path | None
    wav_path: Path | None


# ── Controller ───────────────────────────────────────────────────────────────


# Mapeo sección → patcher del core/config_store
_PATCHERS = {
    "device":   patch_device_section,
    "dsp":      patch_dsp_section,
    "display":  patch_display_section,
    "recorder": patch_recorder_section,
    "scanner":  patch_scanner_section,
    "app":      patch_app_section,
}


# Coerción de tipos por sección: claves que esperan int/float en el TOML.
_INT_KEYS: dict[str, set[str]] = {
    "device":  {"sample_rate", "center_freq"},
    "dsp":     {
        "squelch_threshold", "squelch_hang_ms",
        "wbfm_bandwidth", "nbfm_bandwidth", "am_bandwidth",
        "fm_deemphasis_us",
    },
    "scanner": {"freq_start", "freq_end", "freq_step", "dwell_ms"},
}

_FLOAT_KEYS: dict[str, set[str]] = {
    "dsp":     {"volume", "min_snr_db", "pause_resume_snr_db"},
    "scanner": {"min_snr_db", "pause_resume_snr_db"},
    "display": {"freq_span_mhz"},
}


class StorageController:
    """Coordina grabación, bookmarks y persistencia de config.

    Uso típico desde XyzSDRApp::

        self._storage = StorageController(self, self.audio_effects, PRESETS)

        # Action handler:
        def action_record(self):
            self._storage.toggle_recording()

        def action_quit(self):
            if self._storage.is_recording:
                self._storage.stop_recording(log_stopped=False)
            self._prepare_for_exit()
            ...

        # Settings menu (legacy compat):
        def _persist_dsp_config(self, **updates):
            return self._storage.persist_config("dsp", **updates)

    Args:
        host: implementa StorageHost.
        audio_effects: objeto con métodos play_blip, play_chime, play_error.
        presets: lista de Bookmark fallback si var/bookmarks.toml no existe.
    """

    def __init__(
        self,
        host: StorageHost,
        audio_effects: AudioEffectsLike,
        presets: list[Bookmark],
    ) -> None:
        self._host = host
        self._audio_effects = audio_effects
        self._presets = list(presets)
        # Recorder state
        self._recorder: SDRRecorder | None = None
        self._recording = False
        self._recordings_dir: Path | None = None
        # Bookmarks: carga inicial
        self._bookmarks: list[Bookmark] = self._load_bookmarks()

    # ── Recording ─────────────────────────────────────────────────────────

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def recordings_dir(self) -> Path | None:
        return self._recordings_dir

    def toggle_recording(self) -> None:
        """Inicia o detiene grabación (bind al botón y tecla R)."""
        if self._recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self) -> bool:
        """Inicia grabación IQ + audio si aplica. Devuelve True si OK."""
        if not self._host.rx_active:
            self._audio_effects.play_error()
            self._host.log("[ERROR] Inicia RX antes de grabar")
            return False

        rec_cfg = self._host.config.get("recorder", {})
        self._recordings_dir = resolve_recordings_dir(
            rec_cfg.get("output_dir"),
            project_root=self._host.project_root,
        )
        self._recorder = SDRRecorder(self._recordings_dir)

        dsp_cfg = self._host.config.get("dsp", {})
        audio_rate = int(dsp_cfg.get("audio_rate", 48_000))
        do_iq, do_audio = recording_targets(
            self._host.active_demod_mode,
            record_iq=bool(rec_cfg.get("record_iq", True)),
            record_audio=bool(rec_cfg.get("record_audio", True)),
        )

        try:
            iq_path, wav_path = self._recorder.start(
                center_freq_hz=self._host.tuned_frequency,
                sample_rate_hz=self._host.sample_rate,
                demod_mode=self._host.active_demod_mode,
                audio_rate=audio_rate,
                record_iq=do_iq,
                record_audio=do_audio,
            )
        except Exception as exc:
            self._audio_effects.play_error()
            self._host.log(f"[ERROR] No se pudo iniciar grabacion: {exc}")
            return False

        self._recording = True
        self._audio_effects.play_blip()
        if iq_path:
            self._host.log(f"[OK] Grabacion IQ: {iq_path}")
        if wav_path:
            self._host.log(f"[OK] Grabacion audio: {wav_path}")
        if not iq_path and not wav_path:
            self._recording = False
            self._host.log("[ERROR] Nada que grabar con la config actual")
            return False

        self._host.update_status()
        return True

    def stop_recording(self, log_stopped: bool = True) -> RecordingResult:
        """Detiene grabación y devuelve los paths de los archivos."""
        if not self._recording:
            return RecordingResult(None, None)

        iq_path, wav_path = None, None
        if self._recorder:
            iq_path, wav_path = self._recorder.stop()

        self._recording = False
        if log_stopped:
            self._audio_effects.play_blip()
            if iq_path:
                self._host.log(f"[OK] Grabacion IQ detenida: {iq_path}")
            if wav_path:
                self._host.log(f"[OK] Grabacion audio detenida: {wav_path}")
        self._host.update_status()
        return RecordingResult(iq_path, wav_path)

    # ── Bookmarks ─────────────────────────────────────────────────────────

    @property
    def bookmarks(self) -> list[Bookmark]:
        """Snapshot de los bookmarks actuales."""
        return list(self._bookmarks)

    def bookmarks_path(self) -> Path:
        """Path absoluto a var/bookmarks.toml."""
        return self._host.project_root / "var" / "bookmarks.toml"

    def _load_bookmarks(self) -> list[Bookmark]:
        """Carga bookmarks desde var/bookmarks.toml o usa fallback."""
        return load_bookmarks(self.bookmarks_path(), self._presets)

    def save_current_as_bookmark(self, name: str | None = None) -> Bookmark | None:
        """Guarda la freq/modo actuales como bookmark. Devuelve None si duplicado.

        Args:
            name: nombre del bookmark (default: "Bookmark N").

        Returns:
            El Bookmark creado, o None si ya existía o hubo error.
        """
        # Check duplicate: misma freq ±1 Hz y mismo modo
        for _, freq, mode in self._bookmarks:
            if (
                abs(freq - self._host.tuned_frequency) < 1.0
                and mode == self._host.demod_mode
            ):
                return None

        if name is None:
            name = f"Bookmark {len(self._bookmarks) + 1}"

        bookmark: Bookmark = (
            name,
            self._host.tuned_frequency,
            self._host.demod_mode,
        )
        self._bookmarks.append(bookmark)
        try:
            save_bookmarks(self.bookmarks_path(), self._bookmarks)
            self._host.log(f"[OK] Guardado bookmark: {name}")
            return bookmark
        except Exception as exc:
            self._host.log(f"[ERROR] Guardar bookmark: {exc}")
            return None

    def export_bookmarks_to(self, dest: str | Path) -> bool:
        """Exporta los bookmarks actuales a un archivo TOML."""
        dest_path = self._resolve_bookmark_io_path(dest)
        try:
            export_bookmarks(self._bookmarks, dest_path)
            self._host.log(
                f"[OK] Bookmarks exportados ({len(self._bookmarks)}) → {dest_path}"
            )
            self._audio_effects.play_chime()
            return True
        except Exception as exc:
            self._host.log(f"[ERROR] Export bookmarks: {exc}")
            self._audio_effects.play_error()
            return False

    def import_bookmarks_from(self, src: str | Path, merge: bool = True) -> bool:
        """Importa bookmarks desde TOML. Si merge=True, fusiona con los actuales."""
        src_path = self._resolve_bookmark_io_path(src)
        try:
            imported = import_bookmarks(src_path, self._presets)
            if merge:
                self._bookmarks = merge_bookmarks(self._bookmarks, imported)
            else:
                self._bookmarks = list(imported)
            save_bookmarks(self.bookmarks_path(), self._bookmarks)
            self._host.refresh_preset_select()
            merge_str = " — fusionados" if merge else ""
            self._host.log(
                f"[OK] Bookmarks importados ({len(self._bookmarks)} entradas{merge_str})"
            )
            self._audio_effects.play_chime()
            return True
        except FileNotFoundError:
            self._host.log(f"[ERROR] No se encontró archivo: {src_path}")
            self._audio_effects.play_error()
            return False
        except Exception as exc:
            self._host.log(f"[ERROR] Import bookmarks: {exc}")
            self._audio_effects.play_error()
            return False

    def _resolve_bookmark_io_path(self, path: str | Path) -> Path:
        """Resuelve path: absoluto directo, relativo a project_root."""
        p = Path(str(path).strip())
        if not p.is_absolute():
            p = self._host.project_root / p
        return p

    # ── Config persistence (unified) ──────────────────────────────────────

    def persist_config(self, section: str, **updates) -> bool:
        """Unifica los 5 _persist_*_config: guarda una sección del TOML.

        Args:
            section: una de 'device', 'dsp', 'display', 'recorder', 'scanner', 'app'.
            **updates: claves a actualizar en la sección.

        Returns:
            True si se persistió OK, False si hubo error o sección desconocida.

        Coerción:
            - Algunos campos numéricos se convierten a int (sample_rate, etc.)
              o float (volume, min_snr_db) según el esquema conocido.
            - Ver ``_INT_KEYS`` y ``_FLOAT_KEYS``.
        """
        if section not in _PATCHERS:
            self._host.log(f"[WARN] Sección desconocida: {section}")
            return False

        patcher = _PATCHERS[section]
        try:
            coerced = self._coerce_values(section, updates)
            patcher(self._host.config_path, **coerced)
            # Update in-memory dict
            cfg = self._host.config.setdefault(section, {})
            for key, value in updates.items():
                if value is not None:
                    cfg[key] = value
            return True
        except Exception as exc:
            self._host.log(f"[WARN] No se pudo guardar config [{section}]: {exc}")
            return False

    @staticmethod
    def _coerce_values(section: str, updates: dict) -> dict:
        """Aplica coerción de tipos a los valores antes de persistir."""
        coerced = dict(updates)
        for k in _INT_KEYS.get(section, set()):
            if k in coerced and coerced[k] is not None and not isinstance(coerced[k], bool):
                coerced[k] = int(coerced[k])
        for k in _FLOAT_KEYS.get(section, set()):
            if k in coerced and coerced[k] is not None and not isinstance(coerced[k], bool):
                coerced[k] = float(coerced[k])
        return coerced