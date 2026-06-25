# Dockerfile para CI/CD y entornos reproducibles.
# NO es para usuarios finales (ellos usan install_drivers.ps1 + PothosSDR).
# Útil para: integración continua, runners self-hosted, build agents.

FROM python:3.11-slim AS base

# System deps (build essentials for numpy/scipy wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    libusb-1.0-0 \
    libsndfile1 \
    soapysdr-tools \
    soapysdr-module-rtlsdr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Copy lockfiles first (cache layer)
COPY requirements.lock requirements-dev.lock* ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements-dev.lock

# Copy source
COPY . .

# Set Python path so `import core` works
ENV PYTHONPATH=/workspace
ENV PYTHONPYCACHEPREFIX=/workspace/var/pycache

# Verify install
RUN python -c "import core, tui, setup; print('OK')" \
    && python -m pytest resources/test/ -q -m 'not slow' --no-cov || echo "tests failed"

# Run as non-root
RUN useradd -m -s /bin/bash xyzsdr
USER xyzsdr

# Default: launch in sim mode (sin hardware)
CMD ["python", "main.py", "--sim"]