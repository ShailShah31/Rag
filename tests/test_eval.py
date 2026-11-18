from pathlib import Path
import runpy

from repo_rag.chunks import Chunk


EVAL = runpy.run_path(str(Path(__file__).resolve().parents[1] / "eval" / "run_eval.py"))


def test_relevance_is_same_file_and_inclusive_overlap():
    gold = dict(file="a.py", start_line=5, end_line=8)
    relevant = EVAL["overlaps"]
    assert relevant(Chunk("a.py", 2, 5, "python", ""), gold)
    assert not relevant(Chunk("a.py", 2, 4, "python", ""), gold)
    assert not relevant(Chunk("b.py", 5, 8, "python", ""), gold)


def test_metrics_use_first_rank_and_zero_for_misses():
    assert EVAL["metrics"]([1, 3, 5, None]) == {
        "hit@1": "1/4", "hit@3": "2/4", "hit@5": "3/4", "mrr@5": "23/60",
    }
