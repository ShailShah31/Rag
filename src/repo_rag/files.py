"""Discover tracked and nonignored untracked text in a Git worktree."""
import os
from pathlib import Path, PurePosixPath
import re
import subprocess

from .config import RagError
from .secret_scan import credential_path, has_secret


SKIP_DIRS = {
    ".git", ".repo-rag", "chroma", "chroma_db", "node_modules", "venv", ".venv",
    "env", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    ".nox", "dist", "build", "target", "vendor", "vendors", "deps", "site-packages",
    ".next", ".cache", "coverage", "htmlcov",
}
SKIP_NAMES = {
    "package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml",
    "composer.lock", "go.sum", "packages.lock.json",
}
SKIP_SUFFIXES = (
    ".lock", ".lockb", ".lockfile", ".map", ".pb.go", "_pb2.py", "_pb2_grpc.py",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".ico", ".svg", ".pdf",
    ".zip", ".gz", ".tgz", ".jar", ".whl", ".mp3", ".mp4", ".woff", ".woff2",
    ".sqlite", ".sqlite3", ".db", ".pyc", ".so", ".dll", ".exe",
)
GENERATED = re.compile(
    rb"(?im)^[ \t]*(?://|#|/\*+|\*)[ \t]*"
    rb"(?:@generated\b|automatically generated\b|code generated\b.*do not edit)"
)


def git(root, *args):
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, check=True, timeout=60
        ).stdout
    except FileNotFoundError as exc:
        raise RagError("Git executable not found. Install Git and try again.") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise RagError("Git could not read the worktree.") from exc


def repo_root(value):
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except FileNotFoundError as exc:
        raise RagError(f"Repository path does not exist: {value}") from exc
    except (OSError, RuntimeError) as exc:
        raise RagError(f"Cannot resolve repository path: {value}") from exc
    if not path.is_dir():
        raise RagError(f"Repository path is not a directory: {path}")
    try:
        top = git(path, "rev-parse", "--show-toplevel")
    except RagError as exc:
        if isinstance(exc.__cause__, subprocess.CalledProcessError):
            raise RagError(f"Not a Git worktree, or Git refused access: {path}") from exc
        raise
    root = Path(os.fsdecode(top.rstrip(b"\r\n"))).resolve()
    if root != path:
        raise RagError(f"Pass the Git worktree root: {root}")
    return root


def source_files(root, max_bytes, db_dir=None):
    try:
        paths = git(root, "ls-files", "-co", "--exclude-standard", "-z").split(b"\0")
        if db_dir:
            try:
                database = db_dir.resolve().relative_to(root).as_posix()
            except ValueError:
                database = None
            if database:
                paths = [p for p in paths if os.fsdecode(p) != database
                         and not os.fsdecode(p).startswith(database + "/")]
        for raw in sorted(set(paths)):
            if not raw:
                continue
            rel = os.fsdecode(raw)
            pure = PurePosixPath(rel)
            if (
                pure.is_absolute() or ".." in pure.parts
                or any(part in SKIP_DIRS for part in pure.parts)
                or pure.name in SKIP_NAMES
                or pure.name.endswith(SKIP_SUFFIXES)
                or credential_path(rel)
            ):
                continue
            path = root.joinpath(*pure.parts)
            if path.is_symlink() or not path.is_file():
                continue
            try:
                with path.open("rb") as handle:
                    data = handle.read(max_bytes + 1)
                if (
                    len(data) > max_bytes
                    or any(byte < 32 and byte not in (9, 10, 12, 13) for byte in data)
                    or GENERATED.search(data[:2048]) or has_secret(data)
                ):
                    continue
                text = data.decode("utf-8-sig")
            except (OSError, UnicodeDecodeError, RuntimeError):
                continue
            if text.strip():
                yield rel, text
    except RagError:
        raise
