# xyz-sdr — habilita WER LocalDumps para python.exe (evidencia segfault SDRplay)
param(
    [string]$DumpFolder = "",
    [int]$DumpType = 2,
    [switch]$StatusOnly
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent

if (-not $DumpFolder) {
    $DumpFolder = Join-Path $Root "var\log\dumps"
}

$DumpFolder = [System.IO.Path]::GetFullPath($DumpFolder)
[void][System.IO.Directory]::CreateDirectory($DumpFolder)

$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPy)) {
    throw "venv missing: $VenvPy"
}

Push-Location -LiteralPath $Root
try {
    if ($StatusOnly) {
        & $VenvPy -c "from core.sdrplay_wer import wer_status; import json; print(json.dumps(wer_status(), indent=2))"
        exit 0
    }

    & $VenvPy -c @"
from core.sdrplay_wer import enable_wer_minidumps, wer_status
from pathlib import Path
ok, msg = enable_wer_minidumps(dumps_dir=Path(r'$DumpFolder'), dump_type=$DumpType)
print(msg)
import sys
sys.exit(0 if ok else 1)
"@
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
