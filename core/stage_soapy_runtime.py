"""xyz-sdr | core/stage_soapy_runtime.py — subset Soapy desde Pothos a drivers/win-x64/soapy."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from core.driver_runtime import bundled_manifest_path, bundled_soapy_dir, bundled_win_x64_dir
from core.runtime_paths import project_root
from core.soapy_runtime import POTHOS_CANDIDATES, find_pothos_install

# Archivos típicos Pothos 2021.07.25 / SoapySDR 0.8 (amd64)
DEFAULT_STAGE_FILES: tuple[str, ...] = (
    "SoapySDR.dll",
    "SoapySDRUtil.exe",
    "pthreadVC2.dll",
    "libusb-1.0.dll",
    "libwinpthread-1.dll",
)


def resolve_pothos_bin(pothos_root: str | Path | None = None) -> Path | None:
    if pothos_root:
        candidate = Path(pothos_root) / "bin"
        return candidate if candidate.is_dir() else None
    root = find_pothos_install()
    if root:
        candidate = Path(root) / "bin"
        return candidate if candidate.is_dir() else None
    for base in POTHOS_CANDIDATES:
        candidate = Path(base) / "bin"
        if candidate.is_dir():
            return candidate
    return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stage_soapy_subset(
    *,
    pothos_bin: Path | None = None,
    dest_dir: Path | None = None,
    files: tuple[str, ...] | None = None,
    dry_run: bool = False,
    root: Path | None = None,
) -> dict:
    """Copia subset Soapy a drivers/win-x64/soapy/ y actualiza manifest."""
    src_bin = pothos_bin or resolve_pothos_bin()
    if src_bin is None:
        raise FileNotFoundError(
            "PothosSDR bin no encontrado. Instala Pothos o pasa --pothos-root."
        )

    names = files or DEFAULT_STAGE_FILES
    out_dir = dest_dir or bundled_soapy_dir(root)
    out_dir.mkdir(parents=True, exist_ok=True)

    copied: list[dict[str, object]] = []
    missing: list[str] = []

    for name in names:
        src = src_bin / name
        if not src.is_file():
            missing.append(name)
            continue
        dest = out_dir / name
        if not dry_run:
            shutil.copy2(src, dest)
        stat = src.stat()
        copied.append(
            {
                "name": name,
                "size_bytes": stat.st_size,
                "sha256": _sha256_file(src) if not dry_run else None,
                "source": str(src.resolve()),
            }
        )

    if "SoapySDR.dll" not in {item["name"] for item in copied}:
        raise FileNotFoundError(f"SoapySDR.dll no encontrado en {src_bin}")

    report = {
        "staged_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_bin": str(src_bin.resolve()),
        "dest_dir": str(out_dir.resolve()),
        "dry_run": dry_run,
        "artifacts": copied,
        "missing_optional": missing,
    }

    if not dry_run:
        _write_manifests(report, root=root)

    return report


def _write_manifests(report: dict, *, root: Path | None = None) -> None:
    win_manifest_path = bundled_manifest_path(root)
    existing: dict = {}
    if win_manifest_path.is_file():
        try:
            loaded = json.loads(win_manifest_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, json.JSONDecodeError):
            existing = {}

    existing["soapy_subset"] = {
        "path": "soapy",
        "staged_at": report.get("staged_at"),
        "source_bin": report.get("source_bin"),
        "artifacts": report.get("artifacts"),
        "missing_optional": report.get("missing_optional"),
    }
    win_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    win_manifest_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")

    runtime_manifest = (root or project_root()) / "resources" / "runtime" / "manifest.json"
    if runtime_manifest.is_file():
        try:
            runtime = json.loads(runtime_manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            runtime = {}
    else:
        runtime = {}

    if isinstance(runtime, dict):
        runtime["status"] = "staged"
        components = runtime.setdefault("components", {})
        if isinstance(components, dict):
            soapy = components.setdefault("soapy_subset", {})
            if isinstance(soapy, dict):
                soapy["path"] = "drivers/win-x64/soapy"
                soapy["artifacts"] = [a.get("name") for a in report.get("artifacts", []) if isinstance(a, dict)]
        runtime_manifest.parent.mkdir(parents=True, exist_ok=True)
        runtime_manifest.write_text(json.dumps(runtime, indent=2) + "\n", encoding="utf-8")


def format_stage_summary(report: dict) -> str:
    lines = [
        "=== xyz-sdr Soapy subset staged ===",
        f"source: {report.get('source_bin')}",
        f"dest:   {report.get('dest_dir')}",
        f"dry_run: {report.get('dry_run')}",
    ]
    for item in report.get("artifacts") or []:
        if isinstance(item, dict):
            lines.append(f"  - {item.get('name')} ({item.get('size_bytes')} bytes)")
    missing = report.get("missing_optional") or []
    if missing:
        lines.append(f"missing optional: {', '.join(missing)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage minimal Soapy runtime into drivers/win-x64/soapy/")
    parser.add_argument("--pothos-root", type=Path, default=None, help="PothosSDR install root")
    parser.add_argument("--dest", type=Path, default=None, help="Override destination dir")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    pothos_bin = None
    if args.pothos_root:
        pothos_bin = args.pothos_root / "bin"

    try:
        report = stage_soapy_subset(
            pothos_bin=pothos_bin,
            dest_dir=args.dest,
            dry_run=args.dry_run,
        )
    except FileNotFoundError as exc:
        print(f"[XX] {exc}")
        return 1

    print(format_stage_summary(report))
    if args.dry_run:
        print("\n[OK] Dry-run complete (no files copied)")
    else:
        print(f"\n[OK] Manifest: {bundled_manifest_path()}")
        print(f"[OK] Soapy dir: {bundled_soapy_dir()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
