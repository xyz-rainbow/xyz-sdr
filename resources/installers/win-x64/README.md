# SDRplay API — Windows x64 (offline installer)

Optional bundled installer for **SDRplay API v3.15** used by `setup/install_drivers.ps1` and `setup/install_sdrplay_api.bat`.

## File

- `SDRplay_RSP_API-Windows-3.15.exe` (~51 MiB)

Official download: [SDRplay_RSP_API-Windows-3.15.exe](https://www.sdrplay.com/software/SDRplay_RSP_API-Windows-3.15.exe)

## Resolution order

1. This folder (`resources/installers/win-x64/`)
2. `%USERPROFILE%\Downloads\` or `U:\Downloads\`
3. Environment variable `XYZ_SDR_SDRPLAY_INSTALLER` (full path)
4. Download from SDRplay (if network available)

See `manifest.json` for expected size and SHA-256.

## License

SDRplay API is distributed by SDRplay Ltd.; see [sdrplay.com](https://www.sdrplay.com/downloads/).
