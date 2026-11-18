import argparse
from dataclasses import replace
import sys

from .answer import NOT_FOUND, generate
from .chunks import STRATEGIES
from .config import RagError, Settings
from .files import repo_root
from .index import Index


def parser():
    cli = argparse.ArgumentParser(prog="repo-rag", description="Ask questions about a local Git repository.")
    commands = cli.add_subparsers(dest="command", required=True)
    index = commands.add_parser("index", help="build or replace a local index")
    ask = commands.add_parser("ask", help="retrieve passages and generate a cited answer")
    for command in (index, ask):
        command.add_argument("repo", help="path to the Git worktree root")
        command.add_argument("--chunking", choices=STRATEGIES, default="fixed",
                             help="chunking strategy (default: fixed)")
    ask.add_argument("question", help="natural-language question")
    ask.add_argument("--top-k", type=int, help="override the configured retrieval count")
    return cli


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        root = repo_root(args.repo)
        settings = Settings.from_env()
        if args.command == "ask":
            if args.top_k is not None:
                settings = replace(settings, top_k=args.top_k)
            question = args.question.strip()
            if not question or len(question) > 4000:
                raise RagError("Supply a nonempty question of at most 4,000 characters.")
        index = Index(settings)
        if args.command == "index":
            count = index.rebuild(root, args.chunking)
            print(f"Indexed {count} chunks ({args.chunking}).")
        else:
            hits = index.retrieve(root, args.chunking, question, settings.top_k)
            relevant = [hit for hit in hits if hit.distance <= settings.max_distance]
            if not relevant:
                print("repo-rag: no passages met the cosine distance cutoff.", file=sys.stderr)
                print(NOT_FOUND)
            else:
                print(generate(question, relevant, settings))
        return 0
    except RagError as exc:
        print(f"repo-rag: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("repo-rag: interrupted.", file=sys.stderr)
        return 130
