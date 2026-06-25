# drivers/ — runtime portable xyz-sdr (Windows x64)

Carpeta destino para runtime **redistribuible** (plugin Soapy + subset Soapy mínimo).  
**No sustituye** la instalación oficial de SDRplay API (servicio USB + kernel).

Estado: **Fase 2** — layout `drivers/win-x64/` activo; subset Soapy en Fase 3.

---

## Qué puede ir aquí

| Componente | Incluir en repo | Licencia |
|------------|-----------------|----------|
| `win-x64/plugins/sdrPlaySupport.dll` | Sí | MIT (SoapySDRPlay3) |
| `win-x64/soapy/*.dll` (subset) | Fase 3 | Pothos/Soapy — ver LICENSE |
| `win-x64/manifest.json` | Sí | Metadatos sha256 |

## Qué NO va aquí

| Componente | Motivo |
|------------|--------|
| `sdrplay_api.dll` suelta | EULA SDRplay — usar instalador oficial |
| Drivers USB / servicio | Requiere `setup/install_sdrplay_api.bat` |

Instalador offline API: [resources/installers/win-x64/](../resources/installers/win-x64/README.md)

---

## Orden de bootstrap (planificado)

1. `drivers/win-x64/soapy/` — SoapySDR.dll + deps mínimas
2. `drivers/win-x64/plugins/` — sdrPlaySupport.dll
3. Pothos `Program Files` (fallback)
4. `%LOCALAPPDATA%\xyz-sdr\` (cache usuario)

## Stage Soapy subset (Fase 3)

```powershell
.\scripts\stage_soapy_runtime.ps1          # copy from Pothos bin
.\scripts\stage_soapy_runtime.ps1 -DryRun  # preview only
```

Set `XYZ_SDR_ALLOW_POTHOS_PLUGINS=1` to fall back to Pothos module dirs when bundled runtime is staged.

Implementación: [core/driver_runtime.py](../core/driver_runtime.py) + [core/soapy_runtime.py](../core/soapy_runtime.py).

---

## Mantenimiento

Tras compilar plugin en máquina maintainer:

```powershell
.\setup\install_soapy_sdrplay3.ps1 --publish-bundled
```

Destino canónico: `drivers/win-x64/plugins/` (fallback lectura: `resources/bin/win-x64/`).
