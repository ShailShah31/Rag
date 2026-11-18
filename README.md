# repo-rag

A Python CLI that retrieves relevant code from a local Git worktree and answers questions with `path:start-end` citations. Chroma and sentence-transformers run locally. Only `ask`, and only when passages pass the retrieval cutoff, sends the question and selected source passages to Anthropic.

## Setup

Use Python 3.11 or 3.12 and Git 2.28+. From this directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
python -m pytest -q
```

Tests use temporary Git/Chroma data, deterministic fake embeddings, and a fake Anthropic client. They need no model download, API key, or network after dependencies are installed. The first real index may download the embedding model. Use a populated cache or a local model directory to index offline.

Set variables in your environment, or copy `.env.example` to `.env`, edit it privately, and load your own trusted file with `set -a; . ./.env; set +a`. The CLI does not auto-load `.env` or read environment files from a target repo. Keep credentials out of source control. Index only code you are authorized to process, and ask questions only if the selected code can be sent to Anthropic. The filename and token filters are heuristics, not a data-loss prevention tool.

See `.env.example` for configuration variables, including chunk sizes, embedding model, retrieval cutoff, context budget, and Anthropic settings.

## Usage

```sh
repo-rag --help
repo-rag index /path/to/worktree --chunking fixed
repo-rag index /path/to/worktree --chunking syntax
repo-rag ask /path/to/worktree "How is configuration loaded?" --chunking syntax --top-k 5
```

Use the worktree root and the same database directory for `index` and `ask`. Moving a worktree gives it a new collection name. Rebuild after code, chunker settings, or encoder changes. An empty index is an error; a search with no passages below the cutoff prints `not found in the indexed code`.

## Design

- **Discovery:** `git ls-files` supplies tracked and nonignored untracked files. Common dependencies, build outputs, lockfiles, minified assets, credential files, symlinks, oversized files, and binary/non-UTF-8 files are skipped.
- **Chunking:** fixed line windows or Python AST-aware syntax chunks keep function/class definitions and decorators together when practical. Unsupported languages and invalid Python fall back to fixed windows.
- **Storage:** Chroma collections are keyed by worktree and strategy. Rebuilding replaces the collection to avoid stale/deleted files. Rebuilds are not atomic; rerun indexing if interrupted.
- **Generation:** retrieved passages are sent to Anthropic only when they pass the configured similarity cutoff. Answers include source citations, but citation-label validation does not prove every claim is supported.

## Evaluation

The `eval/` directory contains a benchmark with 20 hand-authored questions and gold evidence spans for Pallets' `itsdangerous` 2.2.0 release. Prepare the fixture and review the pinned spans before running the benchmark:

```sh
python eval/run_eval.py --prepare
# Review the gold spans in eval/questions.json.
python eval/run_eval.py --update-readme
```

No measured benchmark results are included yet. The benchmark is limited to one Python repository and line-overlap relevance; it does not establish general retrieval or answer correctness.

## Security

Never commit `.env` or API keys. The staged secret check is a heuristic guardrail, not a substitute for a dedicated secret scanner. Review staged changes before committing.

## License

MIT. See [LICENSE](LICENSE).
