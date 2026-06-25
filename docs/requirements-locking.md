# Lockfiles

Este proyecto usa lockfiles para builds reproducibles, generados con [`uv pip compile`](https://docs.astral.sh/uv/pip/compile/).

## Archivos

| Archivo | Contenido | Uso |
|---------|-----------|-----|
| `requirements.lock` | Runtime: numpy, scipy, sounddevice, soundfile, textual, rich, tomli (con hashes SHA256) | Producción |
| `requirements-dev.lock` | Runtime + dev: añade pytest, pytest-cov, hypothesis (con hashes) | CI, dev local |

> **Excluido del lockfile:** `SoapySDR` — no está en PyPI; se distribuye vía [PothosSDR](https://github.com/pothosware/PothosSDR) (binarios Windows).

## Cómo regenerar

```powershell
# Runtime lockfile (sin SoapySDR)
uv pip compile requirements.txt --generate-hashes -o requirements.lock

# Dev lockfile (runtime + dev)
uv pip compile requirements.txt requirements-dev.txt --generate-hashes -o requirements-dev.lock
```

Si uv no está instalado:

```powershell
pip install uv
```

## Cómo usar

```powershell
# Instalar con verificación de hashes (recomendado para CI)
pip install --require-hashes -r requirements-dev.lock

# Fallback sin hashes (para entornos donde SoapySDR local interfiere)
pip install -r requirements.txt -r requirements-dev.txt
```

## Por qué hash mode

`--require-hashes` garantiza que cada paquete instalado tiene exactamente el SHA256 esperado. Esto protege contra:
- Mirror attacks (paquete "igual" con código troyano).
- Cambios upstream silenciosos (versión retirada + reintroducida con el mismo número).

Trade-off: cualquier bump de versión requiere regenerar el lockfile. El flujo es:

```powershell
# 1. Editar requirements.txt (e.g. textual~=0.65)
# 2. Regenerar lockfile
uv pip compile requirements.txt -o requirements.lock --upgrade-package textual
# 3. Commit ambos
git add requirements.txt requirements.lock
git commit -m "chore(deps): bump textual to 0.65"
```

## CI

`.github/workflows/test.yml` instala vía `requirements-dev.lock` con `--require-hashes` cuando es posible. Si el lockfile falla por incompatibilidad de plataforma, cae al install tradicional.

## Ver también

- [`docs/uv_runtime.md`](../docs/uv_runtime.md) — wrapper de `uv`
- [uv docs — pip compile](https://docs.astral.sh/uv/pip/compile/)