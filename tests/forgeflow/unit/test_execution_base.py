"""Path-boundary unit tests — resolve_workspace_path (spec §11.2)."""

from pathlib import Path

import pytest

from forgeflow.errors import PathEscapeError
from forgeflow.execution.base import resolve_workspace_path


def test_relative_path_resolves_inside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "file.py").write_text("x")
    assert resolve_workspace_path("file.py", workspace) == (workspace / "file.py").resolve()


def test_absolute_path_inside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "a.py").write_text("x")
    assert resolve_workspace_path(str(workspace / "a.py"), workspace) == (workspace / "a.py").resolve()


def test_dotdot_escape_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    with pytest.raises(PathEscapeError):
        resolve_workspace_path("../outside.txt", workspace)


def test_absolute_outside_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("x")
    with pytest.raises(PathEscapeError):
        resolve_workspace_path(str(outside), workspace)


def test_symlink_escape_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("secret")
    link = workspace / "leak.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable on this platform")
    with pytest.raises(PathEscapeError):
        resolve_workspace_path("leak.txt", workspace)


def test_missing_nested_path_stays_within_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    resolved = resolve_workspace_path("new/file.py", workspace)
    assert resolved.is_relative_to(workspace.resolve())
