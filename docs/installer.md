# Installer — xyz-sdr (Windows)

Express setup wizard for SDRplay + PothosSDR + Python `.venv` on Windows.

Entry point: `setup/install_drivers.py` (launched via `setup/install_drivers.ps1` or `setup/install_drivers.bat`).

Index: [README.md](README.md) | Hardware: [hardware.md](hardware.md)

---

## Express menu

| Option | Action |
|--------|--------|
| **[1] Instalar o reparar todo** | Full wizard: git pull → drivers → Python env → verify |
| **[2] Ejecutar xyz-sdr** | Launch app when ready (adds `--sim` if no hardware) |
| **[3] Diagnóstico rápido** | Summary + next step |
| **[A] Avanzado** | Individual steps, verbose check, language |

**Desktop shortcut (after install):**

```powershell
.\setup\install_app.ps1              # escritorio
.\setup\install_app.ps1 -StartMenu   # menú inicio
.\setup\install_app.ps1 -SimShortcut # incluye acceso directo --sim
.\setup\install_app.ps1 -Uninstall
```

Launcher alternativo: `scripts\xyz-sdr.cmd` (doble clic sin abrir PowerShell manualmente).

**Run shortcuts** (`scripts\run.ps1`):

```powershell
.\scripts\run.ps1 -Sim -Debug
.\scripts\run.ps1 -Band fm_broadcast
.\scripts\run.ps1 -Band airband -Freq 121.5
.\scripts\run.ps1 -Check
.\scripts\run.ps1 -ListDev
```

Perfiles de banda: `config/bands/*.toml` — ver [configuration.md](configuration.md).

Headless:

```powershell
.\setup\install_drivers.ps1 --repair --quiet
.\setup\install_drivers.ps1 --check
.\setup\install_drivers.ps1 --check --verbose
```

Logs: `var/log/install-YYYYMMDD-HHMMSS.log` (gitignored).

---

## Wizard steps (option 1 / `--repair`)

```mermaid
flowchart LR
  S1["1 Update code"]
  S2["2 SDR drivers"]
  S3["3 Python env"]
  S4["4 Verify"]
  S1 --> S2 --> S3 --> S4
```

1. **Update code** — `git pull` if repo (optional skip if not git)
2. **SDR drivers** — SDRplay API v3, PothosSDR (skip if already OK)
3. **Python env** — Python 3.9 via winget if needed, create/repair `.venv`, `pip install -r requirements.txt`
4. **Verification** — `probe_environment()` full check

---

## Readiness levels

From `setup/env_state.py`:

| Level | Meaning | Can run |
|-------|---------|---------|
| `pending` | Missing components | Installer only |
| `env_ready` | Soapy imports in `.venv` | `--sim`, installer launch |
| `hardware_ready` | + SDR enumerated | `run.ps1` without `--sim` |

Probe API: `probe_environment()` — used by wizard step 4 and `python setup/check_env.py`.

---

## Python runtime

- **Recommended:** Python **3.9** in `.venv` (Pothos embedded Soapy bindings)
- Also supported: 3.11/3.12 with `pip install SoapySDR`
- `main.py` calls `try_reexec_for_soapy()` to relaunch in `.venv` when needed

See `core/python_runtime.py`, `setup/check_env.py`.

---

## SDRplay verification

The plugin checker (`check_sdrplay_plugin()` in `core/soapy_runtime.py`) requires **stdout** from:

```text
SoapySDRUtil --find=driver=sdrplay
Found device 0
  driver = sdrplay
```

If the service is stopped, enumeration fails even when API files exist.

```powershell
Get-Service SDRplayAPIService
Start-Service SDRplayAPIService   # if Stopped
```

Close **SDRuno** and other SDR apps before testing.

---

## Module layout

| File | Role |
|------|------|
| `setup/install_drivers.py` | CLI entry, `--check`, `--repair`, `--quiet` |
| `setup/install_wizard.py` | 4-step full wizard |
| `setup/install_menu.py` | Interactive Express menu |
| `setup/install_actions.py` | Install SDRplay, Pothos, Python, venv |
| `setup/install_guidance.py` | Next-step hints from blockers |
| `setup/env_state.py` | `probe_environment()`, readiness |
| `setup/check_env.py` | Human-readable diagnostic output |
| `setup/install_i18n.py` | ES/EN strings |
| `setup/install_log.py` | Session logging to `var/log/` |
| `setup/install_app.ps1` | Desktop / Start Menu shortcuts to `scripts/run.ps1` |

---

## Troubleshooting

| Symptom | Action |
|---------|--------|
| Step 3 fails (Python) | Ensure winget Python 3.9 installed; run repair again |
| Verify OK but no sdrplay in list | Start `SDRplayAPIService`, replug USB |
| False plugin OK with service down | Fixed: checker parses stdout only (not error stderr) |
| PATH missing Pothos | New terminal after install, or repair [1] |
| `python main.py` → REPL | Use `.\scripts\run.ps1` (re-exec fix) |

See also [hardware.md](hardware.md).

---

## After install

```powershell
.\scripts\run.ps1 --check
.\scripts\run.ps1 --list-dev
.\scripts\run.ps1 --driver sdrplay --freq 100.6
```
