"""Tests estructurales de tui/storage.py — StorageController headless."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tui.storage import (
    AudioEffectsLike,
    RecordingResult,
    StorageController,
    StorageHost,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_host(**overrides) -> MagicMock:
    """Host mock que satisface StorageHost."""
    host = MagicMock(spec=StorageHost)
    host.config_path = "/tmp/xyz-sdr-test/config/defaults.toml"
    host.config = {
        "device": {"driver": "auto", "sample_rate": 500_000, "center_freq": 100_000_000, "gain": 40.0},
        "dsp": {"volume": 75.0, "squelch_enabled": False, "squelch_threshold": 5, "fm_agc_enabled": True},
        "recorder": {"record_iq": True, "record_audio": True},
        "scanner": {"freq_start": 88_000_000, "freq_end": 108_000_000},
        "display": {"waterfall_auto_level": True},
    }
    host.tuned_frequency = 100_000_000.0
    host.demod_mode = "wbfm"
    host.rx_active = True
    host.sample_rate = 500_000.0
    host.active_demod_mode = "wbfm"
    host.project_root = Path("/tmp/xyz-sdr-test")
    for k, v in overrides.items():
        setattr(host, k, v)
    return host


def _make_audio_effects() -> MagicMock:
    ae = MagicMock(spec=AudioEffectsLike)
    return ae


PRESETS = [("FM Test", 100_000_000.0, "wbfm"), ("ATC", 118_500_000.0, "nbfm")]


# ── Recording ─────────────────────────────────────────────────────────────────


def test_storage_initial_state_not_recording(tmp_path: Path):
    """StorageController arranca sin grabación activa."""
    host = _make_host(project_root=tmp_path)
    storage = StorageController(host, _make_audio_effects(), PRESETS)
    assert storage.is_recording is False
    assert storage.recordings_dir is None


def test_start_recording_requires_rx_active(tmp_path: Path):
    """Si RX no está activo, start_recording debe fallar y reproducir error."""
    host = _make_host(project_root=tmp_path, rx_active=False)
    storage = StorageController(host, _make_audio_effects(), PRESETS)
    result = storage.start_recording()
    assert result is False
    host.host_log.assert_called()
    assert "RX antes de grabar" in host.host_log.call_args_list[0].args[0]


def test_start_recording_calls_recorder_start(tmp_path: Path):
    """start_recording debe invocar SDRRecorder.start y devolver True."""
    host = _make_host(project_root=tmp_path)
    storage = StorageController(host, _make_audio_effects(), PRESETS)

    # Mockear SDRRecorder para evitar I/O real
    from unittest.mock import patch as mock_patch
    fake_iq = tmp_path / "rec.iq"
    fake_wav = tmp_path / "rec.wav"
    with mock_patch("tui.storage.SDRRecorder") as MockRec:
        instance = MockRec.return_value
        instance.start.return_value = (fake_iq, fake_wav)
        result = storage.start_recording()

    assert result is True
    assert storage.is_recording is True
    instance.start.assert_called_once()


def test_start_recording_handles_no_targets(tmp_path: Path):
    """Si recording_targets devuelve (False, False), debe desactivar _recording."""
    host = _make_host(project_root=tmp_path)
    storage = StorageController(host, _make_audio_effects(), PRESETS)

    from unittest.mock import patch as mock_patch
    with mock_patch("tui.storage.SDRRecorder") as MockRec, \
         mock_patch("tui.storage.recording_targets", return_value=(False, False)):
        instance = MockRec.return_value
        instance.start.return_value = (None, None)
        result = storage.start_recording()

    assert result is False
    assert storage.is_recording is False


def test_stop_recording_when_not_active_is_noop(tmp_path: Path):
    """stop_recording sin grabación activa no debe fallar."""
    host = _make_host(project_root=tmp_path)
    storage = StorageController(host, _make_audio_effects(), PRESETS)
    result = storage.stop_recording()
    assert result.iq_path is None
    assert result.wav_path is None


def test_toggle_recording_starts_when_stopped(tmp_path: Path):
    """toggle_recording alterna entre start y stop."""
    host = _make_host(project_root=tmp_path)
    storage = StorageController(host, _make_audio_effects(), PRESETS)

    from unittest.mock import patch as mock_patch
    fake_iq = tmp_path / "rec.iq"
    fake_wav = tmp_path / "rec.wav"
    with mock_patch("tui.storage.SDRRecorder") as MockRec:
        instance = MockRec.return_value
        instance.start.return_value = (fake_iq, fake_wav)
        instance.stop.return_value = (fake_iq, fake_wav)
        storage.toggle_recording()
        assert storage.is_recording is True
        storage.toggle_recording()
        assert storage.is_recording is False


# ── Bookmarks ─────────────────────────────────────────────────────────────────


def test_storage_loads_initial_bookmarks(tmp_path: Path):
    """StorageController carga bookmarks al inicializar (vía load_bookmarks)."""
    host = _make_host(project_root=tmp_path)
    storage = StorageController(host, _make_audio_effects(), PRESETS)
    # load_bookmarks crea el archivo si no existe, devolviendo los presets
    assert len(storage.bookmarks) == 2
    assert storage.bookmarks[0] == ("FM Test", 100_000_000.0, "wbfm")


def test_bookmarks_path_uses_project_root(tmp_path: Path):
    """bookmarks_path debe ser project_root / var / bookmarks.toml."""
    host = _make_host(project_root=Path("/foo/bar"))
    storage = StorageController(host, _make_audio_effects(), PRESETS)
    assert storage.bookmarks_path() == Path("/foo/bar/var/bookmarks.toml")


def test_save_bookmark_appends(tmp_path: Path):
    """save_current_as_bookmark debe añadir un nuevo bookmark."""
    host = _make_host(project_root=tmp_path, tuned_frequency=101_500_000.0, demod_mode="nbfm")
    storage = StorageController(host, _make_audio_effects(), PRESETS)
    initial_count = len(storage.bookmarks)
    bookmark = storage.save_current_as_bookmark(name="Madrid 101.5")
    assert bookmark is not None
    assert bookmark[0] == "Madrid 101.5"
    assert bookmark[1] == 101_500_000.0
    assert bookmark[2] == "nbfm"
    assert len(storage.bookmarks) == initial_count + 1


def test_save_bookmark_rejects_duplicate(tmp_path: Path):
    """No debe añadir bookmark duplicado (misma freq ±1 Hz + mismo modo)."""
    host = _make_host(
        project_root=tmp_path,
        tuned_frequency=100_000_000.0,  # freq de "FM Test" en PRESETS
        demod_mode="wbfm",
    )
    storage = StorageController(host, _make_audio_effects(), PRESETS)
    bookmark = storage.save_current_as_bookmark(name="Duplicado")
    assert bookmark is None  # rechazado


def test_save_bookmark_default_name(tmp_path: Path):
    """Sin name, debe autogenerar 'Bookmark N'."""
    host = _make_host(project_root=tmp_path, tuned_frequency=102_000_000.0, demod_mode="am")
    storage = StorageController(host, _make_audio_effects(), PRESETS)
    bookmark = storage.save_current_as_bookmark()
    assert bookmark[0].startswith("Bookmark ")


def test_export_bookmarks_to(tmp_path: Path):
    """export_bookmarks_to debe escribir archivo y loguear."""
    host = _make_host(project_root=tmp_path)
    storage = StorageController(host, _make_audio_effects(), PRESETS)
    dest = tmp_path / "export.toml"
    result = storage.export_bookmarks_to(dest)
    assert result is True
    assert dest.is_file()


def test_export_bookmarks_to_relative(tmp_path: Path):
    """Path relativo se resuelve contra project_root."""
    host = _make_host(project_root=tmp_path)
    storage = StorageController(host, _make_audio_effects(), PRESETS)
    result = storage.export_bookmarks_to("my_bookmarks.toml")
    assert result is True
    assert (tmp_path / "my_bookmarks.toml").is_file()


def test_import_bookmarks_from(tmp_path: Path):
    """import_bookmarks_from debe leer archivo y fusionar por defecto."""
    host = _make_host(project_root=tmp_path)
    storage = StorageController(host, _make_audio_effects(), PRESETS)
    src = tmp_path / "import.toml"
    # Crear archivo con un bookmark nuevo
    from core.bookmarks import save_bookmarks
    save_bookmarks(src, [("Custom 1", 200_000_000.0, "am")])

    initial_count = len(storage.bookmarks)
    result = storage.import_bookmarks_from(src, merge=True)
    assert result is True
    assert len(storage.bookmarks) == initial_count + 1


def test_import_bookmarks_from_missing_file(tmp_path: Path):
    """Archivo inexistente debe devolver False sin lanzar."""
    host = _make_host(project_root=tmp_path)
    storage = StorageController(host, _make_audio_effects(), PRESETS)
    result = storage.import_bookmarks_from(tmp_path / "nonexistent.toml")
    assert result is False
    host.host_log.assert_called()


def test_import_bookmarks_from_overwrite_mode(tmp_path: Path):
    """Con merge=False, debe reemplazar la lista en vez de fusionar."""
    host = _make_host(project_root=tmp_path)
    storage = StorageController(host, _make_audio_effects(), PRESETS)
    src = tmp_path / "import.toml"
    from core.bookmarks import save_bookmarks
    save_bookmarks(src, [("Only One", 150_000_000.0, "nbfm")])

    result = storage.import_bookmarks_from(src, merge=False)
    assert result is True
    assert len(storage.bookmarks) == 1
    assert storage.bookmarks[0][0] == "Only One"


# ── Config persistence (unified) ────────────────────────────────────────────


def test_persist_config_unknown_section(tmp_path: Path):
    """Sección desconocida → False + log warning."""
    host = _make_host(project_root=tmp_path)
    storage = StorageController(host, _make_audio_effects(), PRESETS)
    result = storage.persist_config("nonexistent", foo="bar")
    assert result is False


@pytest.mark.parametrize("section,updates", [
    ("device", {"driver": "sdrplay", "sample_rate": 1_024_000.0}),
    ("dsp", {"volume": 80.0, "squelch_threshold": 10.0}),
    ("recorder", {"record_iq": False, "record_audio": True}),
    ("scanner", {"freq_start": 88_000_000, "freq_end": 108_000_000, "dwell_ms": 250}),
    ("display", {"waterfall_auto_level": False}),
])
def test_persist_config_sections(tmp_path: Path, section, updates):
    """Cada sección válida persiste correctamente."""
    import tomli_w
    import sys
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib

    # Crear config file real
    cfg_file = tmp_path / "config" / "defaults.toml"
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    cfg_file.write_text("[device]\ndriver = \"auto\"\n", encoding="utf-8")

    host = _make_host(
        project_root=tmp_path,
        config_path=str(cfg_file),
    )
    storage = StorageController(host, _make_audio_effects(), PRESETS)

    result = storage.persist_config(section, **updates)
    assert result is True, f"persist_config({section}) falló"

    # Verificar que se escribió el TOML
    with cfg_file.open("rb") as f:
        data = tomllib.load(f)
    for k, v in updates.items():
        if v is None:
            continue
        # Coerción: en el TOML, los ints se quedan ints
        if isinstance(v, float) and not isinstance(v, bool):
            # Verificar valor aproximado (tomli_w normaliza)
            assert abs(data[section][k] - v) < 1e-9, f"{section}.{k}: {data[section][k]} != {v}"
        else:
            assert data[section][k] == v, f"{section}.{k}: {data[section][k]} != {v}"


def test_persist_config_updates_in_memory_dict(tmp_path: Path):
    """persist_config debe actualizar tanto TOML como self.config."""
    cfg_file = tmp_path / "config" / "defaults.toml"
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    cfg_file.write_text("[dsp]\nvolume = 50.0\n", encoding="utf-8")

    host = _make_host(project_root=tmp_path, config_path=str(cfg_file))
    storage = StorageController(host, _make_audio_effects(), PRESETS)

    storage.persist_config("dsp", volume=99.0)
    assert host.config["dsp"]["volume"] == 99.0  # in-memory


def test_persist_config_handles_missing_file(tmp_path: Path):
    """Si config_path no existe, debe loguear warning sin lanzar."""
    cfg_file = tmp_path / "nonexistent.toml"
    host = _make_host(project_root=tmp_path, config_path=str(cfg_file))
    storage = StorageController(host, _make_audio_effects(), PRESETS)

    # patch_device_section loguea warning y retorna (no raise)
    result = storage.persist_config("device", driver="sdrplay")
    # El comportamiento depende del patcher; solo verificar que no lanza
    assert isinstance(result, bool)


# ── Coercion helpers ────────────────────────────────────────────────────────


def test_coerce_values_int_keys():
    """_INT_KEYS se convierten a int."""
    coerced = StorageController._coerce_values(
        "device", {"sample_rate": 2_048_000.5, "driver": "sdrplay"}
    )
    assert coerced["sample_rate"] == 2_048_000  # truncado
    assert coerced["driver"] == "sdrplay"  # string intacto


def test_coerce_values_float_keys():
    """_FLOAT_KEYS se convierten a float."""
    coerced = StorageController._coerce_values(
        "dsp", {"volume": "75", "squelch_enabled": False}
    )
    assert coerced["volume"] == 75.0
    assert coerced["squelch_enabled"] is False  # bool no se convierte


def test_coerce_values_unknown_section_passthrough():
    """Sección sin _INT_KEYS ni _FLOAT_KEYS deja intacto."""
    coerced = StorageController._coerce_values(
        "recorder", {"record_iq": True, "record_audio": True}
    )
    assert coerced == {"record_iq": True, "record_audio": True}


# ── AudioEffectsLike protocol ───────────────────────────────────────────────


def test_audio_effects_protocol_minimal():
    """AudioEffectsLike solo requiere play_blip/chime/error."""

    class FakeAE:
        def play_blip(self): pass
        def play_chime(self): pass
        def play_error(self): pass

    ae = FakeAE()
    # No raise, satisfactoria para duck typing
    assert hasattr(ae, "play_blip")
    assert hasattr(ae, "play_chime")
    assert hasattr(ae, "play_error")