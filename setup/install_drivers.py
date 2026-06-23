import os
import sys
import subprocess
import socket
import locale

# Forzar salida UTF-8 en Windows para evitar UnicodeEncodeError al imprimir caracteres ASCII art
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Asegurar que el directorio de trabajo es el del propio script para soportar cualquier ruta
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir:
    os.chdir(os.path.join(script_dir, ".."))

# Habilitar soporte ANSI en Windows de forma nativa
if os.name == 'nt':
    os.system('')

# Paleta Estética Cyberpunk / RAINBOWTECHNOLOGY
C_LIME = "\033[38;5;118m"      # Lime Green
C_PINK = "\033[38;5;207m"      # Cyber Pink
C_CYAN = "\033[38;5;81m"       # Neon Cyan
C_PURPLE = "\033[38;5;141m"    # Neon Purple
C_ORANGE = "\033[38;5;202m"     # Neon Orange
C_RED = "\033[38;5;196m"        # Fire Red
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_GRAY = "\033[90m"

# Diccionario de Traducciones para soporte Español / Inglés
T = {
    "es": {
        "title": "INSTALADOR DE COMPONENTES Y CONTROLADORES XYZ-SDR",
        "status_device": "ESTADO DEL ENTORNO DE RADIO",
        "sdrplay_label": "SDRplay RSP API v3.x",
        "pothos_label": "PothosSDR (SoapySDR, Drivers & PATH)",
        "path_label": "Configuración de PATH de SoapySDR",
        "py_libs_label": "Dependencias Python Core",
        "status_installed": "YA INSTALADO",
        "status_missing": "NO DETECTADO",
        "status_incomplete": "INCOMPLETO (Faltan: {})",
        
        "menu_opt_sdrplay": "Instalar SDRplay API v3.x",
        "menu_opt_pothos": "Instalar PothosSDR (Configura SoapySDR + PATH automáticamente)",
        "menu_opt_py": "Instalar Dependencias de Python (-r requirements.txt)",
        "menu_opt_diag": "Ejecutar Diagnóstico Completo (check_env.py)",
        "menu_opt_lang": "Cambiar Idioma / Change Language (Español)",
        "menu_opt_exit": "Salir",
        
        "select_option": "Selecciona una opción: ",
        "press_enter_menu": "Presiona Enter para volver al menú...",
        "press_enter_exit": "Presiona Enter para salir...",
        
        "downloading": "Descargando {}...",
        "running_installer": "Ejecutando instalador (acepta los permisos de administrador)...",
        "install_success": "Instalación completada con éxito.",
        "install_fail": "Error durante el proceso de instalación/descarga.",
        "path_success": "Ruta añadida con éxito: {}",
        "path_already": "Las rutas ya se encuentran configuradas en el PATH del usuario.",
        "path_fail": "No se pudo configurar el PATH de manera automática: {}",
        "py_checking_uv": "Detectando gestor de paquetes uv...",
        "py_installing_uv": "Instalando uv (gestor de paquetes rápido)...",
        "py_installing_deps": "Instalando paquetes con {}...",
        "py_success": "Dependencias de Python instaladas correctamente.",
        "py_fail": "Hubo un error al instalar los paquetes de Python.",
        "diag_running": "Iniciando análisis del entorno con check_env.py...",
    },
    "en": {
        "title": "XYZ-SDR COMPONENT & DRIVER INSTALLER",
        "status_device": "RADIO ENVIRONMENT STATUS",
        "sdrplay_label": "SDRplay RSP API v3.x",
        "pothos_label": "PothosSDR (SoapySDR, Drivers & PATH)",
        "path_label": "SoapySDR PATH Configuration",
        "py_libs_label": "Core Python Dependencies",
        "status_installed": "INSTALLED",
        "status_missing": "NOT DETECTED",
        "status_incomplete": "INCOMPLETE (Missing: {})",
        
        "menu_opt_sdrplay": "Install SDRplay API v3.x",
        "menu_opt_pothos": "Install PothosSDR (Configures SoapySDR + PATH automatically)",
        "menu_opt_py": "Install Python Dependencies (-r requirements.txt)",
        "menu_opt_diag": "Run Full System Diagnostics (check_env.py)",
        "menu_opt_lang": "Change Language / Cambiar Idioma (English)",
        "menu_opt_exit": "Exit",
        
        "select_option": "Select an option: ",
        "press_enter_menu": "Press Enter to return to the menu...",
        "press_enter_exit": "Press Enter to exit...",
        
        "downloading": "Downloading {}...",
        "running_installer": "Running installer (please grant administrator privileges)...",
        "install_success": "Installation completed successfully.",
        "install_fail": "Error during the installation/download process.",
        "path_success": "PATH successfully updated: {}",
        "path_already": "The paths are already configured in the user PATH.",
        "path_fail": "Could not configure PATH automatically: {}",
        "py_checking_uv": "Checking for uv package manager...",
        "py_installing_uv": "Installing uv (fast package manager)...",
        "py_installing_deps": "Installing packages with {}...",
        "py_success": "Python dependencies successfully installed.",
        "py_fail": "There was an error installing the Python packages.",
        "diag_running": "Starting environment diagnostics with check_env.py...",
    }
}

# --- Detectar idioma inicial ---
def detect_system_language():
    if os.name == 'nt':
        try:
            import ctypes
            lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            if lcid:
                name = locale.windows_locale.get(lcid, "")
                if name:
                    lang = name.split('_')[0].lower()
                    if lang in ['es', 'en']:
                        return lang
        except Exception:
            pass
    try:
        lang_code, _ = locale.getdefaultlocale()
        if lang_code:
            lang = lang_code.split('_')[0].lower()
            if lang in ['es', 'en']:
                return lang
    except Exception:
        pass
    return "en"

CURRENT_LANG = detect_system_language()

# --- Lógica de Detección de Componentes ---
def check_sdrplay_installed():
    paths = [
        r"C:\Program Files\SDRplay",
        r"C:\Program Files (x86)\SDRplay",
    ]
    for p in paths:
        if os.path.exists(p):
            return True
    if os.path.exists(r"C:\Windows\System32\sdrplay_api.dll"):
        return True
    if os.name == 'nt':
        try:
            res = subprocess.run(["sc", "query", "sdrplay-api"], capture_output=True, text=True, check=False)
            if "RUNNING" in res.stdout or "STOPPED" in res.stdout:
                return True
        except Exception:
            pass
    return False

def check_pothos_installed():
    paths = [
        r"C:\Program Files\PothosSDR",
        r"C:\Program Files (x86)\PothosSDR",
    ]
    for p in paths:
        if os.path.exists(p):
            return True
    try:
        res = subprocess.run(["SoapySDRUtil", "--find"], capture_output=True, text=True, check=False)
        if res.returncode == 0 or "SoapySDR" in res.stdout:
            return True
    except Exception:
        pass
    return False

def check_path_configured():
    path_env = os.environ.get("PATH", "")
    targets = [
        r"C:\Program Files\PothosSDR\bin",
        r"C:\Program Files\SoapySDR\bin"
    ]
    for t in targets:
        if t.lower() in path_env.lower():
            return True
    return False

def check_python_libs():
    libs = ["numpy", "scipy", "sounddevice", "textual", "rich"]
    installed = []
    missing = []
    for lib in libs:
        try:
            __import__(lib)
            installed.append(lib)
        except ImportError:
            missing.append(lib)
    return installed, missing

# --- Helpers de Descarga e Instalación ---
def download_file(url, filepath, label):
    import urllib.request
    print(f"  {T[CURRENT_LANG]['downloading'].format(label)}")
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req) as response, open(filepath, 'wb') as out_file:
            meta = response.info()
            file_size = int(meta.get("Content-Length", 0))
            if file_size:
                print(f"  Size: {file_size / (1024*1024):.2f} MB")
            
            downloaded = 0
            block_size = 8192
            while True:
                buffer = response.read(block_size)
                if not buffer:
                    break
                downloaded += len(buffer)
                out_file.write(buffer)
                if file_size:
                    percent = downloaded * 100 / file_size
                    print(f"\r  Progress: {percent:.1f}% ({downloaded / (1024*1024):.2f} MB)", end="", flush=True)
            print("\n")
        return True
    except Exception as e:
        print(f"  [XX] Error: {e}\n")
        return False

def configure_path():
    if os.name != 'nt':
        return False, "OS incompatible"
    
    soapy_paths = [
        r"C:\Program Files\PothosSDR\bin",
        r"C:\Program Files\SoapySDR\bin"
    ]
    valid_paths = [p for p in soapy_paths if os.path.exists(p)]
    if not valid_paths:
        return False, "No physical installation directory found"
    
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_ALL_ACCESS)
        try:
            current_path, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current_path = ""
            
        updated = False
        path_list = [p.strip() for p in current_path.split(";") if p.strip()]
        
        for p in valid_paths:
            if not any(x.lower() == p.lower() for x in path_list):
                path_list.append(p)
                updated = True
                
        if updated:
            new_path = ";".join(path_list)
            winreg.SetValueEx(key, "Path", 0, winreg.REG_SZ, new_path)
            try:
                import ctypes
                HWND_BROADCAST = 0xFFFF
                WM_SETTINGCHANGE = 0x001A
                ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment")
            except Exception:
                pass
            return True, valid_paths
        else:
            return True, None
    except Exception as e:
        return False, str(e)

# --- Impresión del Banner y Menú ---
def print_banner():
    os.system('cls' if os.name == 'nt' else 'clear')
    print(f"{C_RED}  ██████╗  ██╗  ██╗ ██╗   ██╗ ███████╗            ███████╗ ██████╗  ██████╗  ██████╗ {C_RESET}")
    print(f"{C_ORANGE}  ██╔═══╝  ╚██╗██╔╝ ╚██╗ ██╔╝ ╚══███╔╝ █████████╗ ██╔════╝ ██╔══██╗ ██╔══██╗ ╚═══██║ {C_RESET}")
    print(f"{C_LIME}  ██║       ╚███╔╝   ╚████╔╝     ███╔╝ ╚════════╝ ███████╗ ██║  ██║ ██████╔╝     ██║ {C_RESET}")
    print(f"{C_CYAN}  ██║       ██╔██╗    ╚██╔╝     ███╔╝  █████████╗ ╚════██║ ██║  ██║ ██╔══██╗     ██║ {C_RESET}")
    print(f"{C_PURPLE}  ██████╗  ██╔╝ ██╗    ██║     ███████╗            ███████║ ██████╔╝ ██║  ██║ ██████║ {C_RESET}")
    print(f"{C_PINK}  ╚═════╝  ╚═╝  ╚═╝    ╚═╝     ╚══════╝            ╚══════╝ ╚═════╝  ╚═╝  ╚═╝ ╚═════╝ {C_RESET}")
    print(f"{C_CYAN} ─────────────────────────────────────────────────────────────────────────────────────────{C_RESET}")

def print_interface():
    print_banner()
    lang = CURRENT_LANG
    
    # Detecciones
    sdrplay_inst = check_sdrplay_installed()
    pothos_inst = check_pothos_installed()
    path_conf = check_path_configured()
    py_inst, py_missing = check_python_libs()
    
    # Formateo de etiquetas de estado
    sdrplay_status = f"{C_LIME}{C_BOLD}[ {T[lang]['status_installed']} ]{C_RESET}" if sdrplay_inst else f"{C_RED}[ {T[lang]['status_missing']} ]{C_RESET}"
    pothos_status = f"{C_LIME}{C_BOLD}[ {T[lang]['status_installed']} ]{C_RESET}" if (pothos_inst and path_conf) else f"{C_RED}[ {T[lang]['status_missing']} ]{C_RESET}"
    
    if not py_missing:
        py_status = f"{C_LIME}{C_BOLD}[ {T[lang]['status_installed']} ]{C_RESET}"
    elif len(py_inst) == 0:
        py_status = f"{C_RED}[ {T[lang]['status_missing']} ]{C_RESET}"
    else:
        py_status = f"{C_ORANGE}[ {T[lang]['status_incomplete'].format(', '.join(py_missing))} ]{C_RESET}"
        
    print(f" {C_BOLD}{T[lang]['status_device']}:{C_RESET}")
    print(f"  ├── {T[lang]['sdrplay_label']}:      {sdrplay_status}")
    print(f"  ├── {T[lang]['pothos_label']}: {pothos_status}")
    print(f"  └── {T[lang]['py_libs_label']}:      {py_status}")
    print(f"{C_CYAN} ─────────────────────────────────────────────────────────────────────────────────────────{C_RESET}")
    
    # Opciones
    print(f" {C_BOLD}MENÚ DE INSTALACIÓN:{C_RESET}")
    
    # Resaltar si ya está instalado
    lbl_sdrplay = f"{C_GRAY}(Ya instalado / Already Installed){C_RESET}" if sdrplay_inst else ""
    lbl_pothos = f"{C_GRAY}(Ya instalado / Already Installed){C_RESET}" if (pothos_inst and path_conf) else ""
    lbl_py = f"{C_GRAY}(Ya instalado / Already Installed){C_RESET}" if not py_missing else ""
    
    print(f"  {C_PINK}[1]{C_RESET} {T[lang]['menu_opt_sdrplay']} {lbl_sdrplay}")
    print(f"  {C_PINK}[2]{C_RESET} {T[lang]['menu_opt_pothos']} {lbl_pothos}")
    print(f"  {C_PINK}[3]{C_RESET} {T[lang]['menu_opt_py']} {lbl_py}")
    print(f"  {C_PINK}[4]{C_RESET} {T[lang]['menu_opt_diag']}")
    print(f"  {C_PINK}[L]{C_RESET} {T[lang]['menu_opt_lang']}")
    print(f"  {C_PINK}[S]{C_RESET} {T[lang]['menu_opt_exit']}")
    print(f"{C_CYAN} ─────────────────────────────────────────────────────────────────────────────────────────{C_RESET}")

def main():
    global CURRENT_LANG
    
    # Temp dirs
    temp_dir = os.environ.get("TEMP", os.environ.get("TMP", "/tmp"))
    
    while True:
        print_interface()
        opc = input(f" {C_BOLD}{T[CURRENT_LANG]['select_option']}{C_RESET}").strip().upper()
        
        if opc == "S":
            print(f"\n{C_PINK}Saliendo de la instalación. ¡Buen código! / Exiting installer. Happy coding!{C_RESET}\n")
            sys.exit(0)
            
        elif opc == "L":
            CURRENT_LANG = "en" if CURRENT_LANG == "es" else "es"
            
        elif opc == "1":
            print(f"\n{C_CYAN}─── {T[CURRENT_LANG]['menu_opt_sdrplay'].upper()} ───{C_RESET}")
            sdrplay_url = "https://www.sdrplay.com/software/SDRplay_RSP_API-Windows-3.15.1.exe"
            sdrplay_file = os.path.join(temp_dir, "SDRplay_API_installer.exe")
            
            if download_file(sdrplay_url, sdrplay_file, "SDRplay API"):
                print(f"  {T[CURRENT_LANG]['running_installer']}")
                try:
                    subprocess.run([sdrplay_file], check=True)
                    print(f"\n{C_LIME}[SUCCESS] {T[CURRENT_LANG]['install_success']}{C_RESET}")
                except Exception as e:
                    print(f"\n{C_RED}[ERROR] {T[CURRENT_LANG]['install_fail']}: {e}{C_RESET}")
            else:
                print(f"\n{C_RED}[ERROR] {T[CURRENT_LANG]['install_fail']}{C_RESET}")
            input(f"\n{T[CURRENT_LANG]['press_enter_menu']}")
            
        elif opc == "2":
            print(f"\n{C_CYAN}─── {T[CURRENT_LANG]['menu_opt_pothos'].upper()} ───{C_RESET}")
            pothos_url = "https://downloads.myriadrf.org/builds/PothosSDR/PothosSDR-2021.07.25-vc16-x64.exe"
            pothos_file = os.path.join(temp_dir, "PothosSDR_installer.exe")
            
            if download_file(pothos_url, pothos_file, "PothosSDR"):
                print(f"  {T[CURRENT_LANG]['running_installer']}")
                try:
                    subprocess.run([pothos_file], check=True)
                    print(f"\n{C_LIME}[SUCCESS] {T[CURRENT_LANG]['install_success']}{C_RESET}")
                    
                    # Configurar PATH automáticamente
                    print(f"\n{C_CYAN}  → {T[CURRENT_LANG]['path_label']}...{C_RESET}")
                    success_path, info_path = configure_path()
                    if success_path:
                        if info_path:
                            print(f"  {C_LIME}[SUCCESS] {T[CURRENT_LANG]['path_success'].format(', '.join(info_path))}{C_RESET}")
                        else:
                            print(f"  {C_LIME}[SUCCESS] {T[CURRENT_LANG]['path_already']}{C_RESET}")
                    else:
                        print(f"  {C_RED}[ERROR] {T[CURRENT_LANG]['path_fail'].format(info_path)}{C_RESET}")
                except Exception as e:
                    print(f"\n{C_RED}[ERROR] {T[CURRENT_LANG]['install_fail']}: {e}{C_RESET}")
            else:
                print(f"\n{C_RED}[ERROR] {T[CURRENT_LANG]['install_fail']}{C_RESET}")
                print(f"\n{C_ORANGE}  Consejo / Tip: Si no se pudo descargar, bájalo manualmente de:")
                print(f"  {pothos_url}{C_RESET}")
            input(f"\n{T[CURRENT_LANG]['press_enter_menu']}")
            
        elif opc == "3":
            print(f"\n{C_CYAN}─── {T[CURRENT_LANG]['menu_opt_py'].upper()} ───{C_RESET}")
            
            # Detectar si uv está disponible
            has_uv = False
            try:
                res = subprocess.run(["uv", "--version"], capture_output=True, text=True, check=False)
                if res.returncode == 0:
                    has_uv = True
            except Exception:
                pass
            
            try:
                if has_uv:
                    cmd_label = "uv"
                    print(f"  {T[CURRENT_LANG]['py_installing_deps'].format('uv')}")
                    # Ejecutar con uv
                    subprocess.run(["uv", "pip", "install", "-r", "requirements.txt", "--system"], check=True)
                else:
                    cmd_label = "pip"
                    print(f"  {T[CURRENT_LANG]['py_installing_deps'].format('pip')}")
                    # Ejecutar con pip estándar
                    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
                print(f"\n{C_LIME}[SUCCESS] {T[CURRENT_LANG]['py_success']}{C_RESET}")
            except Exception as e:
                print(f"\n{C_RED}[ERROR] {T[CURRENT_LANG]['py_fail']}: {e}{C_RESET}")
            input(f"\n{T[CURRENT_LANG]['press_enter_menu']}")
            
        elif opc == "4":
            print(f"\n{C_CYAN}─── {T[CURRENT_LANG]['menu_opt_diag'].upper()} ───{C_RESET}")
            print(f"  {T[CURRENT_LANG]['diag_running']}")
            try:
                subprocess.run([sys.executable, "setup/check_env.py"], check=False)
            except Exception as e:
                print(f"  [XX] Error: {e}")
            input(f"\n{T[CURRENT_LANG]['press_enter_menu']}")
            
        else:
            print(f"\n{C_RED}[ERROR] Opción no válida / Invalid option{C_RESET}")
            time.sleep(1)

if __name__ == "__main__":
    import time
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{C_PINK}Saliendo de la instalación. ¡Buen código! / Exiting installer. Happy coding!{C_RESET}\n")
        sys.exit(0)
