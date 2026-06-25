# SoapySDRPlay3 — Windows x64 (bundled)

Prebuilt `sdrPlaySupport.dll` for **PothosSDR 2021.07.25** (SoapySDR 0.8) on **Windows x64**.

The xyz-sdr installer copies this file to:

`C:\Program Files\PothosSDR\lib\SoapySDR\modules0.8\sdrPlaySupport.dll`

## Requirements (not included here)

- [SDRplay API v3.15+](https://www.sdrplay.com/downloads/) (official installer)
- PothosSDR (installed by `setup/install_drivers.ps1`)

## License

SoapySDRPlay3 is [MIT licensed](https://github.com/pothosware/SoapySDRPlay3/blob/master/LICENSE.txt).

## Refreshing the bundled binary

After building on a maintainer machine:

```powershell
.\setup\install_soapy_sdrplay3.ps1 --publish-bundled
```

Or from Python:

```powershell
python setup/soapy_sdrplay3.py --publish-bundled
```

See `manifest.json` for source commit, size, and SHA-256.
