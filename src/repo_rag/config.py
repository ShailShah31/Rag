"""Configuration loading and validation."""
from dataclasses import dataclass
import os
from pathlib import Path


class RagError(Exception):
    """Expected application error safe to show to a CLI user."""


def _integer(name, default, minimum=1):
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RagError(f"{name} must be an integer") from exc
    if value < minimum:
        raise RagError(f"{name} must be at least {minimum}")
    return value


def _floating(name, default, minimum=0.0):
    raw = os.getenv(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise RagError(f"{name} must be a number") from exc
    if value < minimum:
        raise RagError(f"{name} must be at least {minimum}")
    return value


@dataclass(frozen=True)
class Settings:
    db_dir: Path = Path(os.getenv("REPO_RAG_DB_DIR", ".repo-rag/chroma")).expanduser()
    chunk_lines: int = _integer("REPO_RAG_CHUNK_LINES", 60)
    overlap_lines: int = _integer("REPO_RAG_OVERLAP_LINES", 10, 0)
    max_file_bytes: int = _integer("REPO_RAG_MAX_FILE_BYTES", 262144)
    embedding_model: str = os.getenv(
        "REPO_RAG_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    )
    embedding_revision: str = os.getenv("REPO_RAG_EMBEDDING_REVISION", "")
    top_k: int = _integer("REPO_RAG_TOP_K", 5)
    max_distance: float = _floating("REPO_RAG_MAX_DISTANCE", 0.75)
    context_chars: int = _integer("REPO_RAG_CONTEXT_CHARS", 20000)
    max_tokens: int = _integer("REPO_RAG_MAX_TOKENS", 900)
    api_timeout: int = _integer("REPO_RAG_API_TIMEOUT", 30)
    api_retries: int = _integer("REPO_RAG_API_RETRIES", 2, 0)
    api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    api_model: str = os.getenv("ANTHROPIC_MODEL", "")

    def validate(self):
        if self.overlap_lines >= self.chunk_lines:
            raise RagError("REPO_RAG_OVERLAP_LINES must be smaller than REPO_RAG_CHUNK_LINES")
        if not self.embedding_model.strip():
            raise RagError("REPO_RAG_EMBEDDING_MODEL cannot be empty")
        if not 0 <= self.max_distance <= 2:
            raise RagError("REPO_RAG_MAX_DISTANCE must be between 0 and 2")
        if self.api_timeout < 1:
            raise RagError("REPO_RAG_API_TIMEOUT must be positive")
        if self.api_retries < 0:
            raise RagError("REPO_RAG_API_RETRIES cannot be negative")
        return self


def load_settings():
    return Settings().validate()
