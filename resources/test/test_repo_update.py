"""Tests para setup/repo_update.py"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from setup import repo_update


class CompletedProcess:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_probe_up_to_date(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(repo_update, "git_available", lambda: True)
    monkeypatch.setattr(repo_update, "is_git_repository", lambda root=None: True)
    monkeypatch.setattr(repo_update, "project_root", lambda: tmp_path)

    def fake_git(root, *args, **kwargs):
        mapping = {
            ("rev-parse", "--abbrev-ref", "HEAD"): CompletedProcess(stdout="main\n"),
            ("rev-parse", "--abbrev-ref", "main@{u}"): CompletedProcess(stdout="origin/main\n"),
            ("fetch", "--quiet", "origin", "main"): CompletedProcess(),
            ("rev-list", "--count", "HEAD..origin/main"): CompletedProcess(stdout="0\n"),
            ("rev-parse", "--short", "HEAD"): CompletedProcess(stdout="abc1234\n"),
        }
        return mapping.get(tuple(args), CompletedProcess(returncode=1))

    monkeypatch.setattr(repo_update, "_run_git", fake_git)
    result = repo_update.probe_repo_update(tmp_path)
    assert result.ok is True
    assert result.status == "up_to_date"
    assert result.behind == 0


def test_pull_updates_success(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(repo_update, "git_available", lambda: True)
    monkeypatch.setattr(repo_update, "is_git_repository", lambda root=None: True)
    monkeypatch.setattr(repo_update, "project_root", lambda: tmp_path)

    revs = iter(["abc1234\n", "def5678\n", "abc1234\n", "def5678\n"])

    def fake_git(root, *args, **kwargs):
        if args[:3] == ("rev-parse", "--abbrev-ref", "HEAD"):
            return CompletedProcess(stdout="main\n")
        if args[:3] == ("rev-parse", "--abbrev-ref", "main@{u}"):
            return CompletedProcess(stdout="origin/main\n")
        if args[:4] == ("fetch", "--quiet", "origin", "main"):
            return CompletedProcess()
        if args[:3] == ("rev-list", "--count", "HEAD..origin/main"):
            return CompletedProcess(stdout="2\n")
        if args[:2] == ("rev-parse", "--short"):
            return CompletedProcess(stdout=next(revs))
        if args[:4] == ("pull", "--ff-only", "origin", "main"):
            return CompletedProcess()
        if args[:2] == ("diff", "--name-only"):
            return CompletedProcess(stdout="setup/install_drivers.py\nREADME.md\n")
        return CompletedProcess(returncode=1)

    monkeypatch.setattr(repo_update, "_run_git", fake_git)
    result = repo_update.pull_repo_updates(tmp_path)
    assert result.status == "updated"
    assert result.behind == 2
    assert result.needs_installer_restart is True


def test_needs_installer_restart_docs_only():
    result = repo_update.RepoUpdateResult(
        ok=True,
        status="updated",
        changed_files=["docs/architecture.md"],
    )
    assert result.needs_installer_restart is False


def test_run_repo_update_not_repo(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(repo_update, "project_root", lambda: tmp_path)
    monkeypatch.setattr(repo_update, "git_available", lambda: True)
    monkeypatch.setattr(repo_update, "is_git_repository", lambda root=None: False)
    messages: list[str] = []

    result = repo_update.run_repo_update("es", messages.append)
    assert result.status == "not_repo"
    assert messages


def test_ensure_wizard_restarts_when_needed(monkeypatch):
    updated = repo_update.RepoUpdateResult(
        ok=True,
        status="updated",
        old_rev="aaa",
        new_rev="bbb",
        changed_files=["setup/install_actions.py"],
    )
    monkeypatch.delenv("XYZ_SDR_INSTALL_SKIP_UPDATE", raising=False)
    monkeypatch.setattr(
        repo_update,
        "run_repo_update",
        lambda lang, say, **kwargs: updated,
    )
    restarted = SimpleNamespace(called=False, resume=None)

    def fake_restart(*, resume=None):
        restarted.called = True
        restarted.resume = resume
        raise SystemExit(0)

    monkeypatch.setattr(repo_update, "restart_installer", fake_restart)
    with pytest.raises(SystemExit):
        repo_update.ensure_repo_updated_for_wizard("es", lambda _m: None)
    assert restarted.called is True
    assert restarted.resume == "repair"
