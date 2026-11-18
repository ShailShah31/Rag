import os
import subprocess

import pytest


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "worktree"
    path.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "core.excludesFile", os.devnull], check=True
    )
    return path.resolve()
