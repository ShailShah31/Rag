import subprocess

from repo_rag.cli import main
from repo_rag.files import repo_root, source_files


def test_git_ignore_tracked_exception_and_filters(repo):
    (repo / ".gitignore").write_text("ignored.py\ntracked.py\nnested/*.tmp\n")
    (repo / "nested").mkdir()
    (repo / "nested" / "a.tmp").write_text("ignored")
    (repo / "ignored.py").write_text("ignored")
    (repo / "tracked.py").write_text("usable = True")
    subprocess.run(["git", "-C", str(repo), "add", "-f", "tracked.py"], check=True)
    (repo / "ok.py").write_text("ok = True")
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "main.js").write_text("dependency")
    (repo / ".env").write_text("PRIVATE=value")
    (repo / "big.txt").write_text("x" * 200)
    (repo / "image.txt").write_bytes(b"\x00\x01")
    (repo / "small.min.js").write_text("minified")
    (repo / "poetry.lock").write_text("lock")
    (repo / "generated.py").write_text("# @generated\nstub = True\n")
    assert repo_root(repo) == repo
    assert set(dict(source_files(repo, 128))) == {".gitignore", "tracked.py", "ok.py"}


def test_cli_expected_path_errors(tmp_path, capsys):
    assert main(["index", str(tmp_path / "missing")]) == 1
    assert "does not exist" in capsys.readouterr().err
    assert main(["index", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "Not a Git worktree" in err
    assert "Traceback" not in err
