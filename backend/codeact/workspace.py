from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

_RUN_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


@dataclass
class WorkspaceSnapshot:
    workspace: Path
    _temporary_directory: tempfile.TemporaryDirectory[str]
    _closed: bool = False

    @property
    def contents(self) -> Path:
        return Path(self._temporary_directory.name) / "contents"

    def restore(self) -> None:
        if self._closed:
            raise RuntimeError("snapshot is already closed")
        self.workspace.mkdir(parents=True, exist_ok=True)
        for child in self.workspace.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
        if self.contents.exists():
            shutil.copytree(self.contents, self.workspace, dirs_exist_ok=True, symlinks=True)

    def close(self) -> None:
        if not self._closed:
            self._temporary_directory.cleanup()
            self._closed = True


@dataclass(frozen=True)
class WorkspaceManager:
    root: Path

    def create(self, run_id: str) -> Path:
        if not _RUN_ID.fullmatch(run_id):
            raise ValueError("run_id must contain only letters, digits, dot, underscore, or hyphen")
        root = self.root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        workspace = root / run_id
        workspace.mkdir(mode=0o700, exist_ok=False)
        return workspace

    def snapshot(self, workspace: Path) -> WorkspaceSnapshot:
        workspace = workspace.resolve()
        if not workspace.is_dir():
            raise ValueError("workspace must be an existing directory")
        temporary_directory = tempfile.TemporaryDirectory(
            prefix=f".{workspace.name}-snapshot-",
            dir=workspace.parent,
        )
        snapshot = WorkspaceSnapshot(workspace, temporary_directory)
        shutil.copytree(workspace, snapshot.contents, symlinks=True)
        return snapshot
