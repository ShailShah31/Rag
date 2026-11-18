"""Line windows and Python structural regions with a shared chunk contract."""
import ast
from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePosixPath


STRATEGIES = ("fixed", "syntax")
DEFS = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
LANGUAGES = {
    ".py": "python", ".js": "javascript", ".mjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".md": "markdown",
    ".yml": "yaml", ".yaml": "yaml", ".rs": "rust", ".sh": "shell",
    ".rb": "ruby", ".cpp": "cpp", ".h": "c",
}


@dataclass(frozen=True)
class Chunk:
    path: str
    start_line: int
    end_line: int
    language: str
    text: str

    @property
    def citation(self):
        return f"{self.path}:{self.start_line}-{self.end_line}"

    @property
    def id(self):
        key = f"{self.path}\0{self.start_line}\0{self.end_line}"
        return sha256(key.encode("utf-8")).hexdigest()

    @property
    def metadata(self):
        return dict(path=self.path, start_line=self.start_line,
                    end_line=self.end_line, language=self.language)


def windows(lo, hi, size, overlap):
    while lo < hi:
        stop = min(hi, lo + size)
        yield lo, stop
        if stop == hi:
            break
        lo = stop - overlap


def regions(lo, hi, body, size):
    """Use zero-based, half-open bounds internally; preserve the gaps."""
    cursor = lo
    for node in body:
        if not isinstance(node, DEFS):
            continue
        start = min([node.lineno, *(d.lineno for d in node.decorator_list)]) - 1
        end = node.end_lineno
        if cursor < start:
            yield cursor, start
        if end - start > size and any(isinstance(child, DEFS) for child in node.body):
            yield from regions(start, end, node.body, size)
        else:
            yield start, end
        cursor = end
    if cursor < hi:
        yield cursor, hi


def syntax_windows(source, spans, size, overlap):
    for lo, hi in spans:
        if not any(line.strip() for line in source[lo:hi]):
            continue
        if hi - lo > size:
            yield from windows(lo, hi, size, overlap)
        else:
            # Use available capacity for preceding context, not for splitting a node.
            yield lo - min(lo, overlap, size - (hi - lo)), hi


def chunk_file(path, text, strategy, size, overlap):
    if strategy not in STRATEGIES or not 0 <= overlap < size:
        raise ValueError("Invalid strategy or window/overlap.")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    source = text.split("\n")
    if source[-1] == "":
        source.pop()
    suffix = PurePosixPath(path).suffix.lower()
    language = LANGUAGES.get(suffix, suffix.lstrip(".") or "text")
    spans = windows(0, len(source), size, overlap)
    if strategy == "syntax" and language == "python":
        try:
            tree = ast.parse(text)
            ast_spans = list(regions(0, len(source), tree.body, size))
        except (SyntaxError, ValueError, RecursionError):
            pass
        else:
            spans = syntax_windows(source, ast_spans, size, overlap)
    for lo, hi in spans:
        content = "\n".join(source[lo:hi])
        if content.strip():
            yield Chunk(path, lo + 1, hi, language, content)
