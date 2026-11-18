"""Heuristic guardrails, not a substitute for a dedicated secret scanner."""
from pathlib import PurePosixPath
import re


TOKEN = re.compile(
    rb"(?:sk-ant-[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{24,}"
    rb"|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    rb"|(?:AKIA|ASIA)[A-Z0-9]{16}|-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----)"
)
KEY_ASSIGNMENT = re.compile(
    rb"(?im)^[ \t]*(?:export[ \t]+)?"
    rb"(?:ANTHROPIC_API_KEY|OPENAI_API_KEY|GH_TOKEN|GITHUB_TOKEN)"
    rb"[ \t]*=[ \t]*['\"]?[A-Za-z0-9_-]{8,}"
)


def has_secret(data):
    return bool(TOKEN.search(data) or KEY_ASSIGNMENT.search(data))


def credential_path(rel):
    parts = [part.lower() for part in PurePosixPath(rel).parts]
    return any(
        p == ".env" or p.startswith(".env.") or p.endswith(".env")
        or p in {".ssh", ".aws", ".netrc", ".npmrc", ".pypirc", "credentials.json",
                 "id_rsa", "id_ed25519"}
        or p.endswith((".pem", ".key", ".p12", ".pfx"))
        for p in parts
    )
