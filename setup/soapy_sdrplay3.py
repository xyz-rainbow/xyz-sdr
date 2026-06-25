"""
xyz-sdr | setup/soapy_sdrplay3.py
Instala SoapySDRPlay3 (plugin Soapy para SDRplay API v3.15+).

Flujo híbrido:
  1. Copia el DLL embebido en resources/bin/win-x64/ (sin compilar).
  2. Si falla o no existe, compila desde fuente (Git, CMake, VS Build Tools vía winget).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_script_dir, ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
if _script_dir:
    os.chdir(_project_root)

from core.soapy_runtime import (
    assess_sdrplay_soapy_module,
    bootstrap_soapy,
    check_sdrplay_plugin,
    find_pothos_install,
    find_sdrplay_api_dll,
    is_sdrplay_soapy_module_ok,
    sync_sdrplay_api_dll_to_pothos,
    user_soapy_plugin_dir,
)
from setup.install_log import log_line
from setup.windows_installers import configure_soapy_plugin_path, configure_user_bin_path, refresh_windows_environment

SOAPY_SDRPLAY3_REPO = "https://github.com/pothosware/SoapySDRPlay3.git"
BUNDLED_DLL_NAME = "sdrPlaySupport.dll"
BUNDLED_DIR = Path(_project_root) / "resources" / "bin" / "win-x64"
BUNDLED_MANIFEST = BUNDLED_DIR / "manifest.json"
CMAKE_GENERATORS = (
    ("Visual Studio 17 2022", "x64"),
    ("Visual Studio 16 2019", "x64"),
)

_EXTRA_PATHS = (
    r"C:\Program Files\CMake\bin",
    r"C:\Program Files\Git\cmd",
    r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\MSBuild\Current\Bin",
    r"C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\MSBuild\Current\Bin",
)


def _say(message: str, log: Callable[[str], None] | None = None) -> None:
    print(message)
    if log:
        log(message)


def command_available(name: str, env: dict[str, str] | None = None) -> bool:
    return shutil.which(name, path=env.get("PATH") if env else None) is not None


def build_env() -> dict[str, str]:
    refresh_windows_environment()
    env = os.environ.copy()
    prepend = [p for p in _EXTRA_PATHS if os.path.isdir(p)]
    pothos = find_pothos_install()
    if pothos:
        prepend.insert(0, os.path.join(pothos, "bin"))
    if prepend:
        env["PATH"] = os.pathsep.join(prepend + [env.get("PATH", "")])
    mod_dir = None
    if pothos:
        soapy_lib = os.path.join(pothos, "lib", "SoapySDR")
        if os.path.isdir(soapy_lib):
            for name in sorted(os.listdir(soapy_lib), reverse=True):
                if name.startswith("modules"):
                    mod_dir = os.path.join(soapy_lib, name)
                    break
    prepend_plugin: list[str] = []
    if mod_dir:
        prepend_plugin.append(mod_dir)
    user_dir = user_soapy_plugin_dir()
    if os.path.isdir(user_dir):
        prepend_plugin.insert(0, user_dir)
    current = env.get("SOAPY_SDR_PLUGIN_PATH", "")
    env["SOAPY_SDR_PLUGIN_PATH"] = os.pathsep.join(
        [p for p in prepend_plugin if p]
        + ([current] if current else [])
    )
    return env


def winget_available(env: dict[str, str] | None = None) -> bool:
    if command_available("winget", env):
        return True
    local = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WindowsApps", "winget.exe")
    return os.path.isfile(local)


def _winget_executable(env: dict[str, str]) -> str:
    found = shutil.which("winget", path=env.get("PATH"))
    if found:
        return found
    return os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WindowsApps", "winget.exe")


def bundled_dll_path() -> Path | None:
    candidate = BUNDLED_DIR / BUNDLED_DLL_NAME
    if not candidate.is_file():
        return None
    try:
        if candidate.stat().st_size < 32_768:
            return None
    except OSError:
        return None
    manifest = load_bundled_manifest()
    if manifest:
        expected_size = manifest.get("size_bytes")
        if isinstance(expected_size, int) and candidate.stat().st_size != expected_size:
            return None
        expected_sha = manifest.get("sha256")
        if isinstance(expected_sha, str) and _sha256_file(candidate) != expected_sha.lower():
            return None
    return candidate


def load_bundled_manifest() -> dict | None:
    if not BUNDLED_MANIFEST.is_file():
        return None
    try:
        return json.loads(BUNDLED_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def needs_soapy_sdrplay3_build() -> bool:
    if is_sdrplay_soapy_module_ok():
        return False
    if check_sdrplay_plugin():
        return False
    status = bootstrap_soapy(force=True)
    module = status.sdrplay_plugin_module
    state = assess_sdrplay_soapy_module(module)
    return state in ("missing", "legacy")


def _run(cmd: list[str], *, env: dict[str, str], cwd: str | None = None) -> int:
    log_line(f"RUN {' '.join(cmd)}")
    proc = subprocess.run(cmd, env=env, cwd=cwd, text=True, check=False)
    return int(proc.returncode)


def install_build_tools_winget(
    *,
    say: Callable[[str], None],
    confirm: Callable[[str], bool] | None = None,
    env: dict[str, str] | None = None,
) -> bool:
    """Instala Git, CMake y VS Build Tools con winget si no están en PATH."""
    env = env or build_env()
    if not winget_available(env):
        say("  [!!] winget no disponible — instala Git, CMake y VS Build Tools manualmente.")
        say("       Git: winget install Git.Git")
        say("       CMake: winget install Kitware.CMake")
        say("       C++: winget install Microsoft.VisualStudio.2022.BuildTools")
        return False

    winget = _winget_executable(env)
    packages: list[tuple[str, str, bool]] = [
        ("Git.Git", "Git", False),
        ("Kitware.CMake", "CMake", False),
        (
            "Microsoft.VisualStudio.2022.BuildTools",
            "Visual Studio 2022 Build Tools (C++)",
            True,
        ),
    ]

    for package_id, label, heavy in packages:
        tool = "git" if "Git" in package_id else "cmake" if "CMake" in package_id else "cl"
        if tool in ("git", "cmake") and command_available(tool, env):
            say(f"  [OK] {label} ya disponible")
            continue
        if tool == "cl" and _has_msvc(env):
            say(f"  [OK] {label} ya disponible")
            continue
        if heavy and confirm is not None:
            if not confirm(
                f"Instalar {label}? (~6 GB, solo si el plugin embebido falla)"
            ):
                say(f"  [!!] Omitido: {label}")
                return False
        say(f"  [>>] Instalando {label} (winget)…")
        code = _run(
            [
                winget,
                "install",
                "--id",
                package_id,
                "-e",
                "--accept-source-agreements",
                "--accept-package-agreements",
            ]
            + (
                [
                    "--override",
                    (
                        "--wait --passive --add Microsoft.VisualStudio.Workload.VCTools "
                        "--includeRecommended"
                    ),
                ]
                if heavy
                else []
            ),
            env=env,
        )
        if code != 0:
            say(f"  [XX] winget falló para {label} (código {code})")
            return False
        env = build_env()

    return command_available("git", env) and command_available("cmake", env) and _has_msvc(env)


def _has_msvc(env: dict[str, str]) -> bool:
    if command_available("cl", env):
        return True
    for root in (
        r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools",
        r"C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools",
        r"C:\Program Files\Microsoft Visual Studio\2022\Community",
    ):
        if os.path.isdir(root):
            return True
    return False


def _module_dir(pothos_root: str) -> Path:
    lib_soapy = Path(pothos_root) / "lib" / "SoapySDR"
    if not lib_soapy.is_dir():
        return lib_soapy / "modules0.8"
    for name in sorted(lib_soapy.iterdir(), reverse=True):
        if name.name.startswith("modules") and name.is_dir():
            return name
    return lib_soapy / "modules0.8"


def _git_head_commit(repo_dir: Path, env: dict[str, str]) -> str | None:
    if not (repo_dir / ".git").is_dir():
        return None
    proc = subprocess.run(
        ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip() or None


def publish_bundled_dll(source: Path, *, say: Callable[[str], None], source_commit: str | None = None) -> bool:
    """Copia un DLL compilado a resources/bin/win-x64/ y escribe manifest.json."""
    if not source.is_file():
        say(f"  [XX] No existe: {source}")
        return False

    BUNDLED_DIR.mkdir(parents=True, exist_ok=True)
    dest = BUNDLED_DIR / BUNDLED_DLL_NAME
    shutil.copy2(source, dest)
    stat = dest.stat()
    manifest = {
        "artifact": BUNDLED_DLL_NAME,
        "platform": "win-x64",
        "target": "PothosSDR 2021.07.25 / SoapySDR 0.8",
        "size_bytes": stat.st_size,
        "sha256": _sha256_file(dest),
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_repo": SOAPY_SDRPLAY3_REPO,
        "source_commit": source_commit,
    }
    BUNDLED_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    say(f"  [OK] Bundled actualizado: {dest} ({stat.st_size} bytes)")
    say(f"  [OK] Manifest: {BUNDLED_MANIFEST}")
    log_line(f"PUBLISH bundled {dest}")
    return True


def _disable_pothos_sdrplay_module(pothos_root: str, *, say: Callable[[str], None]) -> None:
    """Renombra cualquier sdrPlaySupport.dll en Pothos para evitar duplicado con el plugin de usuario."""
    module = _module_dir(pothos_root) / BUNDLED_DLL_NAME
    if not module.is_file():
        return
    disabled = module.with_name(f"{BUNDLED_DLL_NAME}.pothos-disabled")
    suffix = 0
    while disabled.is_file():
        suffix += 1
        disabled = module.with_name(f"{BUNDLED_DLL_NAME}.pothos-disabled-{suffix}")
    try:
        module.rename(disabled)
        say(f"  [OK] Módulo de Pothos desactivado: {disabled.name}")
        log_line(f"DISABLE pothos module {disabled}")
    except OSError:
        say("  [>>] No se pudo desactivar sdrPlaySupport.dll en PothosSDR (puede requerir admin).")


def install_plugin_dll(
    source: Path,
    pothos_root: str,
    *,
    say: Callable[[str], None],
    label: str,
) -> Path | None:
    """Instala el DLL en el perfil del usuario (sin admin) y opcionalmente en Pothos."""
    user_dir = Path(user_soapy_plugin_dir())
    user_dir.mkdir(parents=True, exist_ok=True)
    user_dest = user_dir / BUNDLED_DLL_NAME

    try:
        shutil.copy2(source, user_dest)
    except OSError as exc:
        say(f"  [XX] No se pudo copiar a {user_dest}: {exc}")
        return None

    ok, info = configure_soapy_plugin_path(str(user_dir))
    if ok:
        say(f"  [OK] {label}: {user_dest} ({user_dest.stat().st_size} bytes)")
        say(f"  [OK] SOAPY_SDR_PLUGIN_PATH → {info}")
        refresh_windows_environment()
    else:
        say(f"  [!!] Plugin copiado pero no se registró SOAPY_SDR_PLUGIN_PATH: {info}")

    _disable_pothos_sdrplay_module(pothos_root, say=say)
    return user_dest


def finalize_plugin_install(*, say: Callable[[str], None]) -> bool:
    refresh_windows_environment()
    bootstrap_soapy(force=True)

    if not is_sdrplay_soapy_module_ok():
        say("  [XX] El módulo Soapy sdrplay no quedó instalado correctamente")
        return False

    module = find_pothos_install()
    mod_path = None
    if module:
        from core.soapy_runtime import find_sdrplay_soapy_module

        mod_path = find_sdrplay_soapy_module(module)
    if mod_path:
        say(f"  [OK] Módulo activo: {mod_path}")

    api_dll = find_sdrplay_api_dll()
    pothos_root = find_pothos_install()
    if api_dll and pothos_root:
        sync_sdrplay_api_dll_to_pothos(pothos_root)
        configure_user_bin_path()
        refresh_windows_environment()

    if check_sdrplay_plugin():
        say("  [OK] SoapySDRUtil --find=driver=sdrplay OK")
        return True

    say("  [OK] Plugin instalado (módulo no-legacy presente)")
    say("  [!!] RSP no enumerado aún — cierra SDRuno, reinicia SDRplayAPIService, revisa USB.")
    return True


def install_bundled_soapy_sdrplay3(*, say: Callable[[str], None]) -> bool:
    """Copia el DLL embebido del repositorio a PothosSDR."""
    source = bundled_dll_path()
    if source is None:
        say("  [!!] Plugin embebido no disponible en resources/bin/win-x64/")
        return False

    pothos_root = find_pothos_install()
    if not pothos_root:
        say("  [XX] PothosSDR no encontrado.")
        return False

    manifest = load_bundled_manifest()
    if manifest:
        say(f"  [>>] Plugin embebido ({manifest.get('built_at', '?')}, {source.stat().st_size} bytes)…")
    else:
        say(f"  [>>] Plugin embebido ({source.stat().st_size} bytes)…")

    installed = install_plugin_dll(source, pothos_root, say=say, label="Instalado")
    if installed is None:
        return False
    log_line(f"COPY bundled {source} -> {installed}")
    return finalize_plugin_install(say=say)


def build_and_install_soapy_sdrplay3(
    temp_dir: str,
    *,
    say: Callable[[str], None],
    confirm: Callable[[str], bool] | None = None,
    publish_bundled: bool = False,
) -> bool:
    """Clona, compila e instala SoapySDRPlay3 en PothosSDR."""
    pothos_root = find_pothos_install()
    if not pothos_root:
        say("  [XX] PothosSDR no encontrado. Instala Pothos primero (opción [1] reparar todo).")
        return False

    env = build_env()
    if not command_available("git", env) or not command_available("cmake", env) or not _has_msvc(env):
        say("  [>>] Instalando herramientas de compilación…")
        if not install_build_tools_winget(say=say, confirm=confirm, env=env):
            return False
        env = build_env()

    build_root = Path(temp_dir) / "SoapySDRPlay3-build"
    repo_dir = build_root / "SoapySDRPlay3"
    build_root.mkdir(parents=True, exist_ok=True)

    if not (repo_dir / ".git").is_dir():
        say("  [>>] Clonando SoapySDRPlay3…")
        if _run(["git", "clone", "--depth", "1", SOAPY_SDRPLAY3_REPO, str(repo_dir)], env=env) != 0:
            say("  [XX] git clone falló")
            return False
    else:
        say("  [>>] Actualizando SoapySDRPlay3…")
        _run(["git", "-C", str(repo_dir), "pull", "--ff-only"], env=env)

    build_dir = repo_dir / "build"
    build_dir.mkdir(parents=True, exist_ok=True)

    configured = False
    for generator, arch in CMAKE_GENERATORS:
        say(f"  [>>] CMake ({generator}, {arch})…")
        code = _run(
            [
                "cmake",
                "-G",
                generator,
                "-A",
                arch,
                f"-DCMAKE_PREFIX_PATH={pothos_root}",
                f"-DCMAKE_INSTALL_PREFIX={pothos_root}",
                "..",
            ],
            env=env,
            cwd=str(build_dir),
        )
        if code == 0:
            configured = True
            break

    if not configured:
        say("  [XX] CMake falló. ¿Desktop development with C++ instalado?")
        return False

    say("  [>>] Compilando (Release)…")
    if _run(["cmake", "--build", ".", "--config", "Release"], env=env, cwd=str(build_dir)) != 0:
        say("  [XX] Compilación falló")
        return False

    built_dlls = sorted(
        build_dir.rglob(BUNDLED_DLL_NAME),
        key=lambda p: ("Release" not in str(p), -p.stat().st_mtime),
    )
    release_dlls = [p for p in built_dlls if "Release" in str(p)]
    built = release_dlls[0] if release_dlls else (built_dlls[0] if built_dlls else None)
    if not built or not built.is_file():
        say(f"  [XX] No se encontró {BUNDLED_DLL_NAME} compilado")
        return False

    source_commit = _git_head_commit(repo_dir, env)
    if publish_bundled:
        publish_bundled_dll(built, say=say, source_commit=source_commit)

    try:
        installed = install_plugin_dll(built, pothos_root, say=say, label="Compilado e instalado")
    except PermissionError:
        say("  [!!] Sin permisos para escribir en PothosSDR (ejecuta como administrador).")
        say(f"  [OK] DLL compilado en: {built}")
        return bool(publish_bundled)

    if installed is None:
        return False

    ok = finalize_plugin_install(say=say)
    return ok or bool(publish_bundled)


def install_soapy_sdrplay3_if_needed(
    temp_dir: str,
    *,
    say: Callable[[str], None],
    confirm: Callable[[str], bool] | None = None,
    force: bool = False,
    prefer_build: bool = False,
    publish_bundled: bool = False,
) -> bool:
    if not force and not needs_soapy_sdrplay3_build():
        say("  [OK] Plugin Soapy sdrplay ya operativo")
        log_line("SKIP soapy_sdrplay3")
        return True

    from core.soapy_runtime import check_sdrplay_api

    if not check_sdrplay_api() or not find_pothos_install():
        say("  [!!] Requiere SDRplay API y PothosSDR antes de SoapySDRPlay3")
        return False

    say("\n  → SoapySDRPlay3 (plugin SDRplay para API v3.15+)…")

    if not prefer_build and install_bundled_soapy_sdrplay3(say=say):
        log_line("OK soapy_sdrplay3 bundled")
        return True

    if bundled_dll_path() is not None and not prefer_build:
        say("  [!!] Plugin embebido no pasó verificación — compilando desde fuente…")
    elif prefer_build:
        say("  [>>] Compilación forzada (--build)…")
    else:
        say("  [>>] Sin plugin embebido — compilando desde fuente…")

    return build_and_install_soapy_sdrplay3(
        temp_dir,
        say=say,
        confirm=confirm,
        publish_bundled=publish_bundled,
    )


def _default_confirm(prompt: str) -> bool:
    try:
        answer = input(f"{prompt} [s/N]: ").strip().lower()
    except EOFError:
        return False
    return answer in ("s", "y", "yes", "si", "sí")


def _parse_args(argv: Iterable[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Instala SoapySDRPlay3 para xyz-sdr")
    parser.add_argument("--build", action="store_true", help="Compilar desde fuente (omitir embebido)")
    parser.add_argument(
        "--publish-bundled",
        action="store_true",
        help="Tras compilar, copiar el DLL a resources/bin/win-x64/",
    )
    parser.add_argument(
        "--publish-only",
        metavar="PATH",
        help="Publicar un DLL ya compilado en resources/bin/win-x64/",
    )
    parser.add_argument("-y", "--yes", action="store_true", help="Aceptar instalación de VS Build Tools")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    temp = os.path.join(os.environ.get("TEMP", os.environ.get("TMP", ".")), "xyz-sdr-installer")
    os.makedirs(temp, exist_ok=True)
    confirm = (lambda _prompt: True) if args.yes else _default_confirm

    if args.publish_only:
        ok = publish_bundled_dll(Path(args.publish_only), say=print)
        return 0 if ok else 1

    ok = install_soapy_sdrplay3_if_needed(
        temp,
        say=print,
        confirm=confirm,
        force=True,
        prefer_build=args.build or args.publish_bundled,
        publish_bundled=args.publish_bundled,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
