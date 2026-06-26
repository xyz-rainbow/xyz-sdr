"""Tests for setup/repo_update.py -- git-based self-update helper."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from setup.repo_update import (
    INSTALLER_RESTART_PREFIXES,
    RepoUpdateResult,
    _changed_files_since,
    _commits_behind,
    _current_rev,
    _tracking_branch,
    ensure_repo_updated_for_wizard,
    git_available,
    is_git_repository,
    probe_repo_update,
    pull_repo_updates,
    restart_installer,
    run_repo_update,
)


# ---------------------------------------------------------------------------
# RepoUpdateResult dataclass + properties
# ---------------------------------------------------------------------------


def test_repo_update_result_updated_property() -> None:
    r = RepoUpdateResult(ok=True, status="updated")
    assert r.updated is True
    assert r.needs_installer_restart is False


def test_repo_update_result_not_updated_returns_false() -> None:
    r = RepoUpdateResult(ok=True, status="up_to_date")
    assert r.updated is False


def test_repo_update_result_needs_restart_when_changed_files_match() -> None:
    for prefix in INSTALLER_RESTART_PREFIXES:
        r = RepoUpdateResult(ok=True, status="updated", changed_files=[f"{prefix}foo.py"])
        assert r.needs_installer_restart is True, f"prefix {prefix!r} should trigger restart"


def test_repo_update_result_no_restart_for_unrelated_changes() -> None:
    r = RepoUpdateResult(ok=True, status="updated", changed_files=["README.md", "docs/foo.md"])
    assert r.needs_installer_restart is False


def test_repo_update_result_restart_normalizes_windows_paths() -> None:
    r = RepoUpdateResult(ok=True, status="updated", changed_files=["setup\\installer.py"])
    assert r.needs_installer_restart is True


# ---------------------------------------------------------------------------
# git_available / is_git_repository
# ---------------------------------------------------------------------------


def test_git_available_returns_true_when_on_path(monkeypatch) -> None:
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/git" if cmd == "git" else None)
    assert git_available() is True


def test_git_available_returns_false_when_missing(monkeypatch) -> None:
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    assert git_available() is False


def test_is_git_repository_true_when_dot_git_exists(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    assert is_git_repository(tmp_path) is True


def test_is_git_repository_false_when_no_dot_git(tmp_path: Path) -> None:
    assert is_git_repository(tmp_path) is False


def test_is_git_repository_default_root_uses_project_root() -> None:
    # No tmp_path -> uses project_root(). project_root IS a git repo -> True.
    assert is_git_repository() is True


# ---------------------------------------------------------------------------
# _current_rev / _tracking_branch / _commits_behind / _changed_files_since
# ---------------------------------------------------------------------------


def _fake_proc(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_current_rev_returns_stdout_on_success(tmp_path: Path) -> None:
    with patch(
        "setup.repo_update._run_git",
        return_value=_fake_proc(0, stdout="abc1234\n"),
    ):
        assert _current_rev(tmp_path) == "abc1234"


def test_current_rev_returns_empty_on_failure(tmp_path: Path) -> None:
    with patch(
        "setup.repo_update._run_git", return_value=_fake_proc(1, stderr="error"),
    ):
        assert _current_rev(tmp_path) == ""


def test_tracking_branch_returns_branch_and_upstream(tmp_path: Path) -> None:
    # First call -> branch name; second call -> upstream.
    responses = iter([_fake_proc(0, "main"), _fake_proc(0, "origin/main")])
    with patch("setup.repo_update._run_git", side_effect=lambda *a, **kw: next(responses)):
        branch, upstream = _tracking_branch(tmp_path)
    assert branch == "main"
    assert upstream == "origin/main"


def test_tracking_branch_detached_returns_empty(tmp_path: Path) -> None:
    with patch("setup.repo_update._run_git", return_value=_fake_proc(0, "HEAD")):
        branch, upstream = _tracking_branch(tmp_path)
    assert branch == ""
    assert upstream == ""


def test_tracking_branch_first_call_fails_returns_empty(tmp_path: Path) -> None:
    with patch("setup.repo_update._run_git", return_value=_fake_proc(1)):
        branch, upstream = _tracking_branch(tmp_path)
    assert branch == ""
    assert upstream == ""


def test_tracking_branch_no_upstream_falls_back_to_origin_head(tmp_path: Path) -> None:
    responses = iter([
        _fake_proc(0, "main"),  # branch name
        _fake_proc(1),  # upstream query fails
        _fake_proc(0, "origin/main"),  # origin/HEAD fallback
    ])
    with patch("setup.repo_update._run_git", side_effect=lambda *a, **kw: next(responses)):
        branch, upstream = _tracking_branch(tmp_path)
    assert branch == "main"
    assert upstream == "origin/main"


def test_commits_behind_parses_int(tmp_path: Path) -> None:
    with patch(
        "setup.repo_update._run_git", return_value=_fake_proc(0, stdout="5"),
    ):
        assert _commits_behind(tmp_path, "origin/main") == 5


def test_commits_behind_returns_zero_on_failure(tmp_path: Path) -> None:
    with patch("setup.repo_update._run_git", return_value=_fake_proc(1)):
        assert _commits_behind(tmp_path, "origin/main") == 0


def test_commits_behind_returns_zero_on_garbage(tmp_path: Path) -> None:
    with patch(
        "setup.repo_update._run_git", return_value=_fake_proc(0, stdout="abc"),
    ):
        assert _commits_behind(tmp_path, "origin/main") == 0


def test_commits_behind_returns_zero_on_empty(tmp_path: Path) -> None:
    with patch(
        "setup.repo_update._run_git", return_value=_fake_proc(0, stdout=""),
    ):
        assert _commits_behind(tmp_path, "origin/main") == 0


def test_changed_files_since_returns_lines(tmp_path: Path) -> None:
    with patch(
        "setup.repo_update._run_git",
        return_value=_fake_proc(0, stdout="a.py\nb.py\nc.py\n"),
    ):
        out = _changed_files_since(tmp_path, "old", "new")
    assert out == ["a.py", "b.py", "c.py"]


def test_changed_files_since_returns_empty_for_same_rev(tmp_path: Path) -> None:
    with patch("setup.repo_update._run_git") as mock_git:
        out = _changed_files_since(tmp_path, "abc", "abc")
    assert out == []
    mock_git.assert_not_called()


def test_changed_files_since_returns_empty_on_missing_revs(tmp_path: Path) -> None:
    with patch("setup.repo_update._run_git") as mock_git:
        assert _changed_files_since(tmp_path, "", "new") == []
        assert _changed_files_since(tmp_path, "old", "") == []
    mock_git.assert_not_called()


def test_changed_files_since_returns_empty_on_git_failure(tmp_path: Path) -> None:
    with patch(
        "setup.repo_update._run_git", return_value=_fake_proc(1),
    ):
        assert _changed_files_since(tmp_path, "old", "new") == []


# ---------------------------------------------------------------------------
# probe_repo_update
# ---------------------------------------------------------------------------


def test_probe_repo_update_no_git(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("setup.repo_update.git_available", lambda: False)
    result = probe_repo_update(tmp_path)
    assert result.ok is False
    assert result.status == "no_git"


def test_probe_repo_update_not_git_repo(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("setup.repo_update.git_available", lambda: True)
    monkeypatch.setattr("setup.repo_update.is_git_repository", lambda root: False)
    result = probe_repo_update(tmp_path)
    assert result.ok is False
    assert result.status == "not_repo"


def test_probe_repo_update_detached_head(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("setup.repo_update.git_available", lambda: True)
    monkeypatch.setattr("setup.repo_update.is_git_repository", lambda root: True)
    monkeypatch.setattr("setup.repo_update._tracking_branch", lambda root: ("", ""))
    result = probe_repo_update(tmp_path)
    assert result.ok is False
    assert result.status == "no_branch"


def test_probe_repo_update_fetch_failed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("setup.repo_update.git_available", lambda: True)
    monkeypatch.setattr("setup.repo_update.is_git_repository", lambda root: True)
    monkeypatch.setattr("setup.repo_update._tracking_branch", lambda root: ("main", "origin/main"))
    # First _run_git call is `git fetch` -> returns failure.
    monkeypatch.setattr(
        "setup.repo_update._run_git",
        lambda *a, **kw: _fake_proc(1, stderr="network unreachable"),
    )
    result = probe_repo_update(tmp_path)
    assert result.ok is False
    assert result.status == "fetch_failed"
    assert "network unreachable" in result.error


def test_probe_repo_update_up_to_date(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("setup.repo_update.git_available", lambda: True)
    monkeypatch.setattr("setup.repo_update.is_git_repository", lambda root: True)
    monkeypatch.setattr("setup.repo_update._tracking_branch", lambda root: ("main", "origin/main"))
    # fetch ok
    fetch_calls = []

    def _fake_git(root, *args, **kwargs):
        fetch_calls.append(args)
        if args and args[0] == "rev-list":
            return _fake_proc(0, stdout="0")
        if args and args[0] == "rev-parse":
            return _fake_proc(0, stdout="abc1234")
        return _fake_proc(0, stdout="")

    monkeypatch.setattr("setup.repo_update._run_git", _fake_git)
    result = probe_repo_update(tmp_path)
    assert result.ok is True
    assert result.status == "up_to_date"
    assert result.behind == 0


def test_probe_repo_update_updates_available(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("setup.repo_update.git_available", lambda: True)
    monkeypatch.setattr("setup.repo_update.is_git_repository", lambda root: True)
    monkeypatch.setattr("setup.repo_update._tracking_branch", lambda root: ("main", "origin/main"))

    def _fake_git(root, *args, **kwargs):
        if args and args[0] == "rev-list":
            return _fake_proc(0, stdout="7")
        if args and args[0] == "rev-parse":
            return _fake_proc(0, stdout="abc1234")
        return _fake_proc(0, stdout="")

    monkeypatch.setattr("setup.repo_update._run_git", _fake_git)
    result = probe_repo_update(tmp_path)
    assert result.status == "updates_available"
    assert result.behind == 7


# ---------------------------------------------------------------------------
# pull_repo_updates
# ---------------------------------------------------------------------------


def test_pull_repo_updates_short_circuit_on_no_git(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("setup.repo_update.git_available", lambda: False)
    result = pull_repo_updates(tmp_path)
    assert result.status == "no_git"


def test_pull_repo_updates_returns_probe_when_up_to_date(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("setup.repo_update.probe_repo_update", lambda root: RepoUpdateResult(
        ok=True, status="up_to_date",
    ))
    result = pull_repo_updates(tmp_path)
    assert result.status == "up_to_date"


def test_pull_repo_updates_pull_failed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("setup.repo_update.probe_repo_update", lambda root: RepoUpdateResult(
        ok=True, status="updates_available", behind=3, branch="main", remote="origin/main",
    ))
    # rev-parse ok, then pull fails.
    def _fake_git(root, *args, **kwargs):
        if args and args[0] == "pull":
            return _fake_proc(1, stderr="conflict")
        return _fake_proc(0, stdout="abc")

    monkeypatch.setattr("setup.repo_update._run_git", _fake_git)
    result = pull_repo_updates(tmp_path)
    assert result.status == "pull_failed"
    assert "conflict" in result.error


def test_pull_repo_updates_success(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("setup.repo_update.probe_repo_update", lambda root: RepoUpdateResult(
        ok=True, status="updates_available", behind=2, branch="main", remote="origin/main",
    ))
    responses_by_args = {
        ("rev-parse", "--short", "HEAD"): _fake_proc(0, stdout="newrev12"),
        ("rev-list", "--count", "HEAD..origin/main"): _fake_proc(0, stdout="0"),
        ("diff", "--name-only", "oldrev", "newrev12"): _fake_proc(0, stdout="setup/foo.py\n"),
        ("pull", "--ff-only", "origin", "main"): _fake_proc(0, stdout="Updating"),
    }

    def _fake_git(root, *args, **kwargs):
        return responses_by_args.get(tuple(args), _fake_proc(0, stdout=""))

    # Two rev-parse calls (old + new): both should return same/different.
    rev_calls = [_fake_proc(0, stdout="oldrev"), _fake_proc(0, stdout="newrev12")]
    rev_iter = iter(rev_calls)

    def _fake_git_with_revs(root, *args, **kwargs):
        if args and args[0] == "rev-parse":
            return next(rev_iter)
        return responses_by_args.get(tuple(args), _fake_proc(0, stdout=""))

    monkeypatch.setattr("setup.repo_update._run_git", _fake_git_with_revs)
    result = pull_repo_updates(tmp_path)
    assert result.status == "updated"
    assert result.old_rev == "oldrev"
    assert result.new_rev == "newrev12"
    assert "setup/foo.py" in result.changed_files


# ---------------------------------------------------------------------------
# run_repo_update
# ---------------------------------------------------------------------------


def test_run_repo_update_no_git_returns_no_git(monkeypatch) -> None:
    monkeypatch.setattr("setup.repo_update.git_available", lambda: False)
    messages: list[str] = []

    def _say(m: str) -> None:
        messages.append(m)

    result = run_repo_update("es", _say)
    assert result.status == "no_git"
    assert any("SKIP" in m for m in messages)


def test_run_repo_update_not_repo_returns_not_repo(monkeypatch) -> None:
    monkeypatch.setattr("setup.repo_update.git_available", lambda: True)
    monkeypatch.setattr("setup.repo_update.is_git_repository", lambda root: False)
    messages: list[str] = []

    def _say(m: str) -> None:
        messages.append(m)

    result = run_repo_update("es", _say)
    assert result.status == "not_repo"
    assert any("SKIP" in m for m in messages)


def test_run_repo_update_fetch_failed_says_warn(monkeypatch) -> None:
    monkeypatch.setattr("setup.repo_update.git_available", lambda: True)
    monkeypatch.setattr("setup.repo_update.is_git_repository", lambda root: True)
    monkeypatch.setattr(
        "setup.repo_update.probe_repo_update",
        lambda root: RepoUpdateResult(ok=False, status="fetch_failed", error="boom"),
    )
    messages: list[str] = []

    def _say(m: str) -> None:
        messages.append(m)

    result = run_repo_update("es", _say)
    assert result.status == "fetch_failed"
    assert any("WARN" in m for m in messages)


def test_run_repo_update_up_to_date_says_ok(monkeypatch) -> None:
    monkeypatch.setattr("setup.repo_update.git_available", lambda: True)
    monkeypatch.setattr("setup.repo_update.is_git_repository", lambda root: True)
    monkeypatch.setattr(
        "setup.repo_update.probe_repo_update",
        lambda root: RepoUpdateResult(
            ok=True, status="up_to_date", old_rev="abc1234",
        ),
    )
    messages: list[str] = []

    def _say(m: str) -> None:
        messages.append(m)

    result = run_repo_update("es", _say)
    assert result.status == "up_to_date"
    assert any("OK" in m for m in messages)


def test_run_repo_update_pull_failed_wizard_mode_says_continue(monkeypatch) -> None:
    monkeypatch.setattr("setup.repo_update.git_available", lambda: True)
    monkeypatch.setattr("setup.repo_update.is_git_repository", lambda root: True)

    def _probe(root):
        return RepoUpdateResult(
            ok=True, status="updates_available", behind=3, branch="main",
        )

    def _pull(root):
        return RepoUpdateResult(
            ok=False, status="pull_failed", error="merge conflict",
        )

    monkeypatch.setattr("setup.repo_update.probe_repo_update", _probe)
    monkeypatch.setattr("setup.repo_update.pull_repo_updates", _pull)
    messages: list[str] = []

    def _say(m: str) -> None:
        messages.append(m)

    result = run_repo_update("es", _say, wizard=True)
    assert result.status == "pull_failed"
    # Spanish i18n key 'update_continue_anyway' -> 'Continuando el setup con la versión local…'
    assert any("continuando" in m.lower() or "versión local" in m.lower() for m in messages)


def test_run_repo_update_success_interactive_says_restart_menu(monkeypatch) -> None:
    monkeypatch.setattr("setup.repo_update.git_available", lambda: True)
    monkeypatch.setattr("setup.repo_update.is_git_repository", lambda root: True)

    def _probe(root):
        return RepoUpdateResult(
            ok=True, status="updates_available", behind=2, branch="main",
        )

    def _pull(root):
        return RepoUpdateResult(
            ok=True, status="updated", old_rev="a", new_rev="b",
            changed_files=["setup/foo.py"],
        )

    monkeypatch.setattr("setup.repo_update.probe_repo_update", _probe)
    monkeypatch.setattr("setup.repo_update.pull_repo_updates", _pull)
    messages: list[str] = []

    def _say(m: str) -> None:
        messages.append(m)

    result = run_repo_update("es", _say, interactive=True)
    assert result.status == "updated"
    assert any("SUCCESS" in m for m in messages)
    # Spanish i18n key 'update_restart_menu' -> 'Reiniciando instalador para cargar cambios…'
    assert any("reiniciando" in m.lower() or "instalador" in m.lower() for m in messages)


# ---------------------------------------------------------------------------
# restart_installer
# ---------------------------------------------------------------------------


def test_restart_installer_sets_skip_update_env_and_exits(
    monkeypatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "setup.repo_update.project_root", lambda: tmp_path,
    )
    monkeypatch.setattr(
        "setup.repo_update.log_line", lambda msg: None,
    )
    fake_popen = patch(
        "setup.repo_update.subprocess.Popen",
        return_value=None,
    )
    with patch("setup.repo_update.sys.exit", side_effect=SystemExit) as mock_exit:
        with fake_popen as mock_popen_fn:
            with pytest.raises(SystemExit):
                restart_installer()
    # Environment must include the skip flag.
    call_args = mock_popen_fn.call_args
    env = call_args.kwargs["env"]
    assert env["XYZ_SDR_INSTALL_SKIP_UPDATE"] == "1"
    mock_exit.assert_called_once_with(0)


def test_restart_installer_with_resume_passes_env(
    monkeypatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr("setup.repo_update.project_root", lambda: tmp_path)
    monkeypatch.setattr("setup.repo_update.log_line", lambda msg: None)
    with patch("setup.repo_update.subprocess.Popen", return_value=None) as mock_popen:
        with patch("setup.repo_update.sys.exit", side_effect=SystemExit):
            try:
                restart_installer(resume="repair")
            except SystemExit:
                pass
    env = mock_popen.call_args.kwargs["env"]
    assert env["XYZ_SDR_INSTALL_RESUME"] == "repair"
    assert env["XYZ_SDR_INSTALL_SKIP_UPDATE"] == "1"


# ---------------------------------------------------------------------------
# ensure_repo_updated_for_wizard
# ---------------------------------------------------------------------------


def test_ensure_repo_updated_returns_none_when_skip_set(monkeypatch) -> None:
    monkeypatch.setattr("os.environ", {"XYZ_SDR_INSTALL_SKIP_UPDATE": "1"})
    result = ensure_repo_updated_for_wizard("es", lambda m: None)
    assert result is None


def test_ensure_repo_updated_triggers_restart_when_installer_changed(monkeypatch) -> None:
    monkeypatch.delenv("XYZ_SDR_INSTALL_SKIP_UPDATE", raising=False)
    monkeypatch.setattr("setup.repo_update.git_available", lambda: True)
    monkeypatch.setattr("setup.repo_update.is_git_repository", lambda root: True)
    monkeypatch.setattr(
        "setup.repo_update.probe_repo_update",
        lambda root: RepoUpdateResult(
            ok=True, status="updates_available", behind=2, branch="main",
        ),
    )
    monkeypatch.setattr(
        "setup.repo_update.pull_repo_updates",
        lambda root: RepoUpdateResult(
            ok=True, status="updated", old_rev="a", new_rev="b",
            changed_files=["setup/install_actions.py"],
        ),
    )
    with patch("setup.repo_update.restart_installer") as mock_restart:
        result = ensure_repo_updated_for_wizard("es", lambda m: None)
    assert result is not None
    assert result.updated is True
    mock_restart.assert_called_once_with(resume="repair")


def test_ensure_repo_updated_no_restart_when_changes_outside_installer(monkeypatch) -> None:
    monkeypatch.delenv("XYZ_SDR_INSTALL_SKIP_UPDATE", raising=False)
    monkeypatch.setattr("setup.repo_update.git_available", lambda: True)
    monkeypatch.setattr("setup.repo_update.is_git_repository", lambda root: True)
    monkeypatch.setattr(
        "setup.repo_update.probe_repo_update",
        lambda root: RepoUpdateResult(
            ok=True, status="updates_available", behind=2, branch="main",
        ),
    )
    monkeypatch.setattr(
        "setup.repo_update.pull_repo_updates",
        lambda root: RepoUpdateResult(
            ok=True, status="updated", old_rev="a", new_rev="b",
            changed_files=["README.md"],
        ),
    )
    with patch("setup.repo_update.restart_installer") as mock_restart:
        result = ensure_repo_updated_for_wizard("es", lambda m: None)
    assert result is not None
    mock_restart.assert_not_called()


def test_ensure_repo_updated_returns_none_when_no_git(monkeypatch) -> None:
    monkeypatch.delenv("XYZ_SDR_INSTALL_SKIP_UPDATE", raising=False)
    monkeypatch.setattr("setup.repo_update.git_available", lambda: False)
    messages: list[str] = []

    def _say(m: str) -> None:
        messages.append(m)

    result = ensure_repo_updated_for_wizard("es", _say)
    assert result is not None
    assert result.status == "no_git"