"""Reproducible retrieval benchmark over a pinned public Git fixture."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "eval" / "questions.json"
REPO = ROOT / "eval" / ".repos" / "itsdangerous"
RESULTS = ROOT / "eval" / "results"


def run_git(*args, cwd=None):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def load_questions():
    return json.loads(QUESTIONS.read_text(encoding="utf-8"))


def prepare(data):
    REPO.parent.mkdir(parents=True, exist_ok=True)
    if not REPO.exists():
        run_git("clone", "--filter=blob:none", data["repo_url"], str(REPO))
    run_git("fetch", "--tags", "origin", data["release_tag"], cwd=REPO)
    commit = run_git("rev-parse", f"{data['release_tag']}^{{commit}}", cwd=REPO)
    if commit != data["commit"]:
        raise RuntimeError("Fixture release tag does not resolve to the pinned commit.")
    run_git("checkout", "--detach", commit, cwd=REPO)
    for item in data["questions"]:
        gold = item["gold"]
        source = (REPO / gold["file"]).read_text(encoding="utf-8").splitlines()
        start, end = None, None
        for index, line in enumerate(source, 1):
            if line.startswith(f"def {gold['definition']}(") or line.startswith(
                f"class {gold['definition']}("
            ):
                start = index
                break
        if start is None:
            raise RuntimeError(f"Could not find definition {gold['definition']}")
        end = start
        while end < len(source) and (not source[end].startswith(("def ", "class "))):
            end += 1
        gold["start_line"], gold["end_line"] = start, end
    QUESTIONS.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(data['questions'])} questions against {commit}")


def overlaps(chunk, gold):
    return (
        chunk.path == gold["file"]
        and chunk.start_line <= gold["end_line"]
        and gold["start_line"] <= chunk.end_line
    )


def metrics(ranks):
    n = len(ranks)
    return {
        f"hit@{k}": f"{sum(rank is not None and rank <= k for rank in ranks)}/{n}"
        for k in (1, 3, 5)
    } | {
        "mrr@5": f"{sum(1 / rank for rank in ranks if rank is not None and rank <= 5):.4f}"
    }


def evaluate():
    from repo_rag.config import load_settings
    from repo_rag.index import Index

    data = load_questions()
    cfg = load_settings()
    RESULTS.mkdir(parents=True, exist_ok=True)
    output = {}
    for strategy in ("fixed", "syntax"):
        index = Index(cfg)
        index.rebuild(REPO, strategy)
        ranks = []
        details = []
        for item in data["questions"]:
            hits = index.retrieve(REPO, strategy, item["question"], 5)
            rank = next((i for i, hit in enumerate(hits, 1)
                         if overlaps(hit.chunk, item["gold"])), None)
            ranks.append(rank)
            details.append({
                "id": item["id"],
                "rank": rank,
                "results": [
                    {"citation": hit.chunk.citation, "distance": hit.distance}
                    for hit in hits
                ],
            })
        output[strategy] = {"metrics": metrics(ranks), "questions": details}
        (RESULTS / f"{strategy}.json").write_text(
            json.dumps(output[strategy], indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps({key: value["metrics"] for key, value in output.items()}, indent=2))
    return output


def update_readme(results):
    start, end = "<!-- eval:start -->", "<!-- eval:end -->"
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = [
        start,
        "| Strategy | Hit@1 | Hit@3 | Hit@5 | MRR@5 |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, result in results.items():
        m = result["metrics"]
        section.append(
            f"| {name} | {m['hit@1']} | {m['hit@3']} | {m['hit@5']} | {m['mrr@5']} |"
        )
    section.append(end)
    before = readme.index(start)
    after = readme.index(end, before) + len(end)
    (ROOT / "README.md").write_text(
        readme[:before] + "\n".join(section) + readme[after:],
        encoding="utf-8",
    )


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--update-readme", action="store_true")
    args = parser.parse_args(argv)
    try:
        data = load_questions()
        if args.prepare:
            prepare(data)
        else:
            if not REPO.exists():
                raise RuntimeError("Run with --prepare first.")
            if run_git("rev-parse", "HEAD", cwd=REPO) != data["commit"]:
                raise RuntimeError("Fixture checkout does not match the pinned commit.")
            results = evaluate()
            if args.update_readme:
                update_readme(results)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"evaluation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
