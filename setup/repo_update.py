"""Actualización del repositorio xyz-sdr vía git (fetch + pull)."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from setup.env_state import project_root
from setup.install_i18n import t
from setup.install_log import log_line

INSTALLER_RESTART_PREFIXES = ("setup/", "scripts/", "core/", "main.py", "config/", "requirements.txt")


@dataclass
class RepoUpdateResult:
    ok: bool
    status: str
    behind: int = 0
    branch: str = ""
    remote: str = ""
    old_rev: str = ""
    new_rev: str = ""
    changed_files: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def updated(self) -> bool:
        return self.status == "updated"

    @property
    def needs_installer_restart(self) -> bool:
        if not self.updated:
            return False
        for path in self.changed_files:
            normalized = path.replace("\\", "/")
            if normalized.startswith(INSTALLER_RESTART_PREFIXES):
                return True
        return False


def git_available() -> bool:
    import shutil

    return shutil.which("git") is not None


def is_git_repository(root: Path | None = None) -> bool:
    root = root or project_root()
    return (root / ".git").is_dir()


def _run_git(root: Path, *args: str, timeout: float = 120.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _current_rev(root: Path) -> str:
    result = _run_git(root, "rev-parse", "--short", "HEAD")
    return result.stdout.strip() if result.returncode == 0 else ""


def _tracking_branch(root: Path) -> tuple[str, str]:
    branch = _run_git(root, "rev-parse", "--abbrev-ref", "HEAD")
    name = branch.stdout.strip() if branch.returncode == 0 else ""
    if not name or name == "HEAD":
        return "", ""

    upstream = _run_git(root, "rev-parse", "--abbrev-ref", f"{name}@{{u}}")
    if upstream.returncode != 0:
        upstream = _run_git(root, "rev-parse", "--abbrev-ref", "origin/HEAD")
    remote_ref = upstream.stdout.strip() if upstream.returncode == 0 else f"origin/{name}"
    return name, remote_ref


def _commits_behind(root: Path, upstream: str) -> int:
    result = _run_git(root, "rev-list", "--count", f"HEAD..{upstream}")
    if result.returncode != 0:
        return 0
    try:
        return int(result.stdout.strip() or "0")
    except ValueError:
        return 0


def _changed_files_since(root: Path, old_rev: str, new_rev: str) -> list[str]:
    if not old_rev or not new_rev or old_rev == new_rev:
        return []
    result = _run_git(root, "diff", "--name-only", old_rev, new_rev)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def probe_repo_update(root: Path | None = None) -> RepoUpdateResult:
    root = root or project_root()
    if not git_available():
        return RepoUpdateResult(ok=False, status="no_git")
    if not is_git_repository(root):
        return RepoUpdateResult(ok=False, status="not_repo")

    branch, upstream = _tracking_branch(root)
    if not branch:
        return RepoUpdateResult(ok=False, status="no_branch", error="detached HEAD")

    fetch = _run_git(root, "fetch", "--quiet", "origin", branch)
    if fetch.returncode != 0:
        detail = (fetch.stderr or fetch.stdout or "").strip()
        return RepoUpdateResult(
            ok=False,
            status="fetch_failed",
            branch=branch,
            remote=upstream,
            error=detail[:240],
        )

    behind = _commits_behind(root, upstream)
    return RepoUpdateResult(
        ok=True,
        status="updates_available" if behind > 0 else "up_to_date",
        behind=behind,
        branch=branch,
        remote=upstream,
        old_rev=_current_rev(root),
    )


def pull_repo_updates(root: Path | None = None) -> RepoUpdateResult:
    root = root or project_root()
    probe = probe_repo_update(root)
    if probe.status in ("no_git", "not_repo", "no_branch", "fetch_failed"):
        return probe
    if probe.status == "up_to_date":
        return probe

    old_rev = _current_rev(root)
    pull = _run_git(root, "pull", "--ff-only", "origin", probe.branch)
    if pull.returncode != 0:
        detail = (pull.stderr or pull.stdout or "").strip()
        return RepoUpdateResult(
            ok=False,
            status="pull_failed",
            branch=probe.branch,
            remote=probe.remote,
            behind=probe.behind,
            old_rev=old_rev,
            error=detail[:240],
        )

    new_rev = _current_rev(root)
    changed = _changed_files_since(root, old_rev, new_rev)
    return RepoUpdateResult(
        ok=True,
        status="updated",
        behind=probe.behind,
        branch=probe.branch,
        remote=probe.remote,
        old_rev=old_rev,
        new_rev=new_rev,
        changed_files=changed,
    )


def restart_installer(*, resume: str | None = None) -> None:
    root = project_root()
    script = root / "setup" / "install_drivers.py"
    env = os.environ.copy()
    env["XYZ_SDR_INSTALL_SKIP_UPDATE"] = "1"
    if resume:
        env["XYZ_SDR_INSTALL_RESUME"] = resume

    log_line(f"Restarting installer resume={resume or 'menu'}")
    subprocess.Popen([sys.executable, str(script)], env=env, cwd=str(root))
    sys.exit(0)


def run_repo_update(
    lang: str,
    say: Callable[[str], None],
    *,
    interactive: bool = False,
    wizard: bool = False,
) -> RepoUpdateResult:
    root = project_root()
    say(f"  {t(lang, 'update_checking')}")

    if not git_available():
        say(f"  [SKIP] {t(lang, 'update_no_git')}")
        return RepoUpdateResult(ok=False, status="no_git")

    if not is_git_repository(root):
        say(f"  [SKIP] {t(lang, 'update_not_repo')}")
        return RepoUpdateResult(ok=False, status="not_repo")

    probe = probe_repo_update(root)
    if probe.status == "fetch_failed":
        say(f"  [WARN] {t(lang, 'update_fetch_failed').format(probe.error or '?')}")
        return probe

    if probe.status == "up_to_date":
        rev = probe.old_rev or _current_rev(root)
        say(f"  [OK] {t(lang, 'update_up_to_date').format(rev)}")
        return probe

    say(f"  [INFO] {t(lang, 'update_available').format(probe.behind, probe.branch)}")
    log_line(f"Repo update available: {probe.behind} commits on {probe.branch}")
    say(f"  {t(lang, 'update_pulling')}")

    result = pull_repo_updates(root)
    if result.status == "pull_failed":
        say(f"  [WARN] {t(lang, 'update_failed').format(result.error or '?')}")
        if wizard:
            say(f"  {t(lang, 'update_continue_anyway')}")
        return result

    say(
        f"  [SUCCESS] {t(lang, 'update_success').format(result.old_rev, result.new_rev, len(result.changed_files))}"
    )
    if interactive:
        say(f"  {t(lang, 'update_restart_menu')}")
    elif wizard:
        say(f"  {t(lang, 'update_restart_wizard')}")
    return result


def ensure_repo_updated_for_wizard(lang: str, say: Callable[[str], None]) -> RepoUpdateResult | None:
    if os.environ.get("XYZ_SDR_INSTALL_SKIP_UPDATE"):
        return None

    result = run_repo_update(lang, say, wizard=True)
    if result.updated and result.needs_installer_restart:
        restart_installer(resume="repair")
    return result
