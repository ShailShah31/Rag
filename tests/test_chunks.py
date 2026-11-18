import pytest

from repo_rag.chunks import chunk_file


def bounds(chunks):
    return [(c.start_line, c.end_line) for c in chunks]


def test_fixed_windows_are_inclusive_and_do_not_repeat_tail():
    chunks = list(chunk_file("a.txt", "one\ntwo\nthree\nfour\nfive\n", "fixed", 3, 1))
    assert bounds(chunks) == [(1, 3), (3, 5)]
    assert chunks[1].text == "three\nfour\nfive"
    assert chunks[1].citation == "a.txt:3-5"


def test_python_regions_keep_decorators_and_use_available_overlap():
    src = "# module\n@decorate\ndef first():\n    return 1\n\nasync def second():\n    return 2\n"
    chunks = list(chunk_file("a.py", src, "syntax", 4, 1))
    assert bounds(chunks) == [(1, 1), (1, 4), (5, 7)]
    assert chunks[1].language == "python"
    assert "@decorate\ndef first()" in chunks[1].text


def test_oversized_class_splits_at_methods():
    src = "class A:\n    def a(self):\n        return 1\n\n    def b(self):\n        return 2\n"
    assert bounds(chunk_file("a.py", src, "syntax", 3, 0)) == [(1, 1), (2, 3), (5, 6)]


@pytest.mark.parametrize("path", ["a.js", "a.py"])
def test_syntax_falls_back_for_non_python_and_invalid_python(path):
    src = "def invalid(:\nline 2\nline 3\nline 4\n"
    assert list(chunk_file(path, src, "syntax", 3, 1)) == list(
        chunk_file(path, src, "fixed", 3, 1)
    )
