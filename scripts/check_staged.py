#!/usr/bin/env python3
"""Best-effort staged-file credential guard; not a dedicated secret scanner."""
import re
import subprocess
import sys

PATTERNS = [
    (re.compile(r"(?i)\b(?:sk-ant-[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{24,})\b"), "API token"),
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"), "GitHub token"),
    (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), "cloud access key"),
    (re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"), "private key"),
    (re.compile(r"(?im)^\s*(?:export\s+)?(?:ANTHROPIC_API_KEY|OPENAI_API_KEY|GH_TOKEN|GITHUB_TOKEN)\s*=\s*['\"]?[A-Za-z0-9_-]{8,}"), "credential assignment"),
]


def main():
    try:
        names = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "-z"],
            check=True, capture_output=True,
        ).stdout.split(b"\0")
        failed = False
        for raw in names:
            if not raw:
                continue
            name = raw.decode("utf-8", "surrogateescape")
            lower = name.lower()
            if lower == ".env" or lower.startswith(".env.") or lower.endswith((".pem", ".key", ".p12", ".pfx")):
                print(f"Blocked sensitive staged path: {name}", file=sys.stderr)
                failed = True
                continue
            blob = subprocess.run(
                ["git", "show", f":{name}"], check=True, capture_output=True
            ).stdout
            text = blob.decode("utf-8", "replace")
            for pattern, label in PATTERNS:
                if pattern.search(text):
                    print(f"Possible {label} in staged file: {name}", file=sys.stderr)
                    failed = True
        if failed:
            return 1
        print("Staged-file heuristic secret check passed.")
        return 0
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Could not inspect staged files: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
