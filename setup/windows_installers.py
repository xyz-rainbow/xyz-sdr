"""Descarga, UAC y PATH de Windows para el instalador."""

from __future__ import annotations

import os
import subprocess
import urllib.request

SDRPLAY_INSTALLER_URL = "https://www.sdrplay.com/software/SDRplay_RSP_API-Windows-3.15.exe"
POTHOS_INSTALLER_URL = "https://downloads.myriadrf.org/builds/PothosSDR/PothosSDR-2021.07.25-vc16-x64.exe"


def download_file(url: str, filepath: str, label: str, *, lang: str, on_message) -> bool:
    from setup.install_i18n import t

    on_message(f"  {t(lang, 'downloading').format(label)}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req) as response, open(filepath, "wb") as out_file:
            block_size = 8192
            while True:
                buffer = response.read(block_size)
                if not buffer:
                    break
                out_file.write(buffer)
        return True
    except Exception as exc:
        on_message(f"  [XX] Error: {exc}")
        return False


def is_windows_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run_exe_installer(installer_path: str) -> None:
    installer_path = os.path.abspath(installer_path)
    if not os.path.isfile(installer_path):
        raise FileNotFoundError(installer_path)

    if os.name != "nt":
        subprocess.run([installer_path], check=True)
        return

    if is_windows_admin():
        subprocess.run([installer_path], check=True)
        return

    import ctypes
    from ctypes import wintypes

    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    SW_SHOWNORMAL = 1
    ERROR_CANCELLED = 1223

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("fMask", ctypes.c_ulong),
            ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD),
            ("hMonitor", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE),
        ]

    sei = SHELLEXECUTEINFOW()
    sei.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
    sei.fMask = SEE_MASK_NOCLOSEPROCESS
    sei.lpVerb = "runas"
    sei.lpFile = installer_path
    sei.nShow = SW_SHOWNORMAL

    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei)):
        err = ctypes.GetLastError()
        if err == ERROR_CANCELLED:
            raise PermissionError("UAC cancelled")
        raise OSError(err, "ShellExecuteEx failed")

    ctypes.windll.kernel32.WaitForSingleObject(sei.hProcess, 0xFFFFFFFF)
    exit_code = wintypes.DWORD()
    ctypes.windll.kernel32.GetExitCodeProcess(sei.hProcess, ctypes.byref(exit_code))
    ctypes.windll.kernel32.CloseHandle(sei.hProcess)

    if exit_code.value != 0:
        raise subprocess.CalledProcessError(exit_code.value, installer_path)


def notify_path_environment_changed() -> None:
    """Recarga PATH/PYTHONPATH del registro en el proceso actual."""
    refresh_windows_environment()


def refresh_windows_environment() -> bool:
    """Fusiona PATH del registro (usuario + sistema) y PYTHONPATH en os.environ."""
    if os.name != "nt":
        return False

    from setup.env_state import path_contains_pothos

    import winreg

    registry_path_parts: list[str] = []
    for root, subkey in (
        (winreg.HKEY_CURRENT_USER, "Environment"),
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    ):
        try:
            with winreg.OpenKey(root, subkey) as key:
                value, _ = winreg.QueryValueEx(key, "Path")
                if value:
                    registry_path_parts.extend(p.strip() for p in str(value).split(";") if p.strip())
        except OSError:
            continue

    merged: list[str] = []
    seen: set[str] = set()
    for entry in registry_path_parts + [p for p in os.environ.get("PATH", "").split(";") if p.strip()]:
        key = os.path.normcase(entry)
        if key in seen:
            continue
        seen.add(key)
        merged.append(entry)
    if merged:
        os.environ["PATH"] = ";".join(merged)

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            py_path, _ = winreg.QueryValueEx(key, "PYTHONPATH")
            if py_path:
                os.environ["PYTHONPATH"] = str(py_path)
    except OSError:
        pass

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            plugin_path, _ = winreg.QueryValueEx(key, "SOAPY_SDR_PLUGIN_PATH")
            if plugin_path:
                os.environ["SOAPY_SDR_PLUGIN_PATH"] = str(plugin_path)
    except OSError:
        pass

    for bin_dir in (r"C:\Program Files\PothosSDR\bin", r"C:\Program Files\SoapySDR\bin"):
        if os.path.isdir(bin_dir):
            try:
                os.add_dll_directory(bin_dir)
            except (AttributeError, OSError):
                pass

    try:
        import ctypes
        ctypes.windll.user32.PostMessageW(0xFFFF, 0x001A, 0, "Environment")
    except Exception:
        pass

    return path_contains_pothos(os.environ.get("PATH", ""))


def configure_path() -> tuple[bool, list[str] | str | None]:
    if os.name != "nt":
        return False, "OS incompatible"

    soapy_paths = [
        r"C:\Program Files\PothosSDR\bin",
        r"C:\Program Files\SoapySDR\bin",
    ]
    valid_paths = [p for p in soapy_paths if os.path.exists(p)]
    if not valid_paths:
        return False, "No physical installation directory found"

    added: list[str] = []
    key = None
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_ALL_ACCESS)
        try:
            current_path, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current_path = ""

        path_list = [p.strip() for p in current_path.split(";") if p.strip()]
        path_updated = False
        for entry in valid_paths:
            if not any(x.lower() == entry.lower() for x in path_list):
                path_list.append(entry)
                path_updated = True
                added.append(entry)

        if path_updated:
            winreg.SetValueEx(key, "Path", 0, winreg.REG_SZ, ";".join(path_list))

        try:
            from core.soapy_runtime import get_pothos_site_packages_for_env
            site_packages = get_pothos_site_packages_for_env()
            if site_packages:
                try:
                    current_py, _ = winreg.QueryValueEx(key, "PYTHONPATH")
                except FileNotFoundError:
                    current_py = ""
                py_list = [p.strip() for p in current_py.split(";") if p.strip()]
                if not any(os.path.normcase(x) == os.path.normcase(site_packages) for x in py_list):
                    py_list.append(site_packages)
                    winreg.SetValueEx(key, "PYTHONPATH", 0, winreg.REG_SZ, ";".join(py_list))
                    added.append(f"PYTHONPATH:{site_packages}")
        except Exception:
            pass

        refresh_windows_environment()

        if added:
            return True, added
        return True, None
    except Exception as exc:
        return False, str(exc)
    finally:
        if key is not None:
            try:
                import winreg
                winreg.CloseKey(key)
            except Exception:
                pass


def configure_user_bin_path() -> tuple[bool, str | None]:
    """Añade %LOCALAPPDATA%\\xyz-sdr\\bin al PATH del usuario."""
    if os.name != "nt":
        return False, "OS incompatible"

    from core.soapy_runtime import user_xyz_sdr_bin_dir

    bin_dir = os.path.normpath(user_xyz_sdr_bin_dir())
    os.makedirs(bin_dir, exist_ok=True)

    key = None
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_ALL_ACCESS)
        try:
            current_path, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current_path = ""

        path_list = [p.strip() for p in current_path.split(";") if p.strip()]
        if not any(os.path.normcase(x) == os.path.normcase(bin_dir) for x in path_list):
            path_list.insert(0, bin_dir)
            winreg.SetValueEx(key, "Path", 0, winreg.REG_SZ, ";".join(path_list))

        refresh_windows_environment()
        return True, bin_dir
    except Exception as exc:
        return False, str(exc)
    finally:
        if key is not None:
            try:
                import winreg
                winreg.CloseKey(key)
            except Exception:
                pass


def configure_soapy_plugin_path(plugin_dir: str) -> tuple[bool, str | None]:
    """Registra SOAPY_SDR_PLUGIN_PATH en el entorno del usuario (HKCU)."""
    if os.name != "nt":
        return False, "OS incompatible"

    plugin_dir = os.path.normpath(plugin_dir)
    if not os.path.isdir(plugin_dir):
        return False, "Plugin directory not found"

    key = None
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_ALL_ACCESS)
        try:
            current, _ = winreg.QueryValueEx(key, "SOAPY_SDR_PLUGIN_PATH")
        except FileNotFoundError:
            current = ""

        parts = [p.strip() for p in str(current).split(";") if p.strip()]
        norm_new = os.path.normcase(plugin_dir)
        parts = [p for p in parts if os.path.normcase(os.path.normpath(p)) != norm_new]
        parts.insert(0, plugin_dir)
        winreg.SetValueEx(key, "SOAPY_SDR_PLUGIN_PATH", 0, winreg.REG_SZ, ";".join(parts))
        refresh_windows_environment()
        return True, plugin_dir
    except Exception as exc:
        return False, str(exc)
    finally:
        if key is not None:
            try:
                import winreg
                winreg.CloseKey(key)
            except Exception:
                pass
