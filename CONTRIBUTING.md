**English** | [Español](CONTRIBUTING.es.md)

# Contributing to xyz-sdr

Thanks for taking the time to contribute. Interactive terminal SDR controller (Python, SoapySDR, Textual, NumPy/SciPy) with timeline, FFT, and waterfall views.

## License and contributions

By opening an issue or sending a pull request you accept the contribution clause in [LICENSE](LICENSE): you assign to Rainbow Technology all rights in your contribution, or, if that assignment is not effective, you grant a perpetual, irrevocable, exclusive license, and you warrant that you have the right to contribute it.

Please do not open a public issue for a security vulnerability; use the repository Security advisory form if it is available.

## Development setup

Create a virtualenv and install runtime plus dev dependencies, as in the previous contributing notes:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

CI workflows are `.github/workflows/test.yml` and `.github/workflows/lint.yml`.

## Pull requests

1. Create a topic branch from the default branch (`main`).
2. Keep the change focused.
3. Update [CHANGELOG.md](CHANGELOG.md) and add a line to `docs/logs/YYYY-MM.md` when the change is user-visible or touches process or docs.
4. Never commit secrets, API keys, or private data.
5. Wait for CI to go green when the repository has workflows. Maintainers squash-merge into the default branch.
