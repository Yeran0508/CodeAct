from pathlib import Path

import pytest
from codeact.workspace import WorkspaceManager, validate_workspace


def test_manager_creates_private_unique_workspace(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path)
    workspace = manager.create("run-001")
    assert workspace == tmp_path / "run-001"
    assert workspace.is_dir()
    with pytest.raises(FileExistsError):
        manager.create("run-001")


def test_manager_rejects_path_traversal_run_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="run_id"):
        WorkspaceManager(tmp_path).create("../outside")


def test_snapshot_restores_files_directories_and_symlinks(tmp_path: Path) -> None:
    workspace = WorkspaceManager(tmp_path).create("run")
    (workspace / "original.txt").write_text("before")
    (workspace / "folder").mkdir()
    (workspace / "folder" / "nested.txt").write_text("nested")
    (workspace / "link").symlink_to("original.txt")
    snapshot = WorkspaceManager(tmp_path).snapshot(workspace)

    (workspace / "original.txt").write_text("after")
    (workspace / "created.txt").write_text("created")
    (workspace / "folder" / "nested.txt").unlink()
    snapshot.restore()

    assert (workspace / "original.txt").read_text() == "before"
    assert not (workspace / "created.txt").exists()
    assert (workspace / "folder" / "nested.txt").read_text() == "nested"
    assert (workspace / "link").is_symlink()
    snapshot.close()


def test_closed_snapshot_cannot_restore(tmp_path: Path) -> None:
    workspace = WorkspaceManager(tmp_path).create("run")
    snapshot = WorkspaceManager(tmp_path).snapshot(workspace)
    snapshot.close()
    with pytest.raises(RuntimeError, match="closed"):
        snapshot.restore()


def test_workspace_rejects_symlink_that_escapes_boundary(tmp_path: Path) -> None:
    workspace = WorkspaceManager(tmp_path).create("run")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    (workspace / "escape").symlink_to(outside)
    with pytest.raises(ValueError, match="escapes"):
        validate_workspace(workspace)
