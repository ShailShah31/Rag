from dataclasses import replace

import pytest

from repo_rag.config import RagError, Settings
from repo_rag.index import Index


def fake_encoder(texts):
    return [[1.0, 0.0] if "needle" in text else [0.0, 1.0] for text in texts]


def test_chroma_retrieval_rebuild_isolation_and_empty(repo, tmp_path):
    (repo / "a.py").write_text("needle = 1\n")
    (repo / "b.py").write_text("other = 2\n")
    cfg = replace(Settings(), db_dir=tmp_path / "chroma")
    index = Index(cfg, encode=fake_encoder)
    with pytest.raises(RagError, match="Empty index"):
        index.retrieve(repo, "fixed", "needle", 5)
    assert index.rebuild(repo, "fixed") == 2
    assert index.rebuild(repo, "fixed") == 2
    assert index.rebuild(repo, "syntax") == 2

    reopened = Index(cfg, encode=fake_encoder)
    hits = reopened.retrieve(repo, "fixed", "needle", 5)
    assert [h.chunk.citation for h in hits] == ["a.py:1-1", "b.py:1-1"]
    assert hits[0].distance < hits[1].distance
    assert len(reopened.retrieve(repo, "fixed", "needle", 1)) == 1

    (repo / "a.py").unlink()
    assert reopened.rebuild(repo, "fixed") == 1
    assert reopened.retrieve(repo, "fixed", "needle", 5)[0].chunk.path == "b.py"
    assert len(reopened.retrieve(repo, "syntax", "needle", 5)) == 2

    (repo / "b.py").unlink()
    assert reopened.rebuild(repo, "fixed") == 0
    with pytest.raises(RagError, match="Empty index"):
        reopened.retrieve(repo, "fixed", "needle", 5)
