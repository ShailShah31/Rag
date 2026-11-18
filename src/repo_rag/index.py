"""Persistent, strategy-isolated Chroma indexes and cosine retrieval."""
from dataclasses import dataclass
from hashlib import sha256
from itertools import islice
import os

from .chunks import Chunk, chunk_file
from .config import RagError
from .files import source_files


class LocalEncoder:
    def __init__(self, settings):
        self.settings = settings
        self.model = None

    def __call__(self, texts):
        try:
            if self.model is None:
                from sentence_transformers import SentenceTransformer

                self.model = SentenceTransformer(
                    self.settings.embedding_model,
                    revision=self.settings.embedding_revision or None,
                    trust_remote_code=False,
                    device="cpu",
                )
            return self.model.encode(
                texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False
            ).tolist()
        except Exception as exc:
            raise RagError(
                "Could not load or run the local embedding model. Check the install, "
                "model ID/revision, and first-download access or local cache."
            ) from exc


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    distance: float


def collection_name(root, strategy):
    digest = sha256(os.fsencode(root)).hexdigest()[:24]
    return f"repo-{digest}-{strategy}"


class Index:
    def __init__(self, settings, encode=None):
        self.settings = settings
        self.encode = encode if encode is not None else LocalEncoder(settings)
        try:
            from chromadb import PersistentClient
            from chromadb.config import Settings as ChromaSettings
            from chromadb.errors import NotFoundError

            self.db_dir = settings.db_dir.expanduser().resolve()
            self.client = PersistentClient(
                path=str(self.db_dir), settings=ChromaSettings(anonymized_telemetry=False)
            )
            self.not_found = NotFoundError
        except Exception as exc:
            raise RagError("Could not open Chroma. Check the install and REPO_RAG_DB_DIR.") from exc

    def _get(self, name):
        try:
            return self.client.get_collection(name=name, embedding_function=None)
        except self.not_found:
            return None
        except Exception as exc:
            raise RagError("Could not read the local Chroma collection.") from exc

    def _signature(self):
        return dict(schema=1, embedding_model=self.settings.embedding_model,
                    embedding_revision=self.settings.embedding_revision)

    def rebuild(self, root, strategy):
        cfg = self.settings
        sources = source_files(root, cfg.max_file_bytes, self.db_dir)
        chunks = (
            chunk for path, text in sources
            for chunk in chunk_file(path, text, strategy, cfg.chunk_lines, cfg.overlap_lines)
        )
        # Start iteration before replacing the old collection, so Git discovery
        # failures leave it alone. The rebuild itself is deliberately non-atomic.
        batch = list(islice(chunks, 64))
        name = collection_name(root, strategy)
        metadata = dict(**self._signature(), state="building", lines=cfg.chunk_lines,
                        overlap=cfg.overlap_lines, max_file_bytes=cfg.max_file_bytes)
        try:
            if self._get(name) is not None:
                self.client.delete_collection(name=name)
            collection = self.client.create_collection(
                name=name, embedding_function=None, metadata=metadata,
                configuration={"hnsw": {"space": "cosine"}},
            )
        except Exception as exc:
            raise RagError("Could not replace the local index. Check disk access and retry.") from exc

        total = 0
        while batch:
            documents = [chunk.text for chunk in batch]
            embeddings = self.encode(documents)
            try:
                collection.add(
                    ids=[chunk.id for chunk in batch], documents=documents,
                    metadatas=[chunk.metadata for chunk in batch], embeddings=embeddings,
                )
            except Exception as exc:
                raise RagError("Could not write a Chroma batch. Re-run index to rebuild.") from exc
            total += len(batch)
            batch = list(islice(chunks, 64))
        try:
            collection.modify(metadata={**metadata, "state": "ready"})
        except Exception as exc:
            raise RagError("Could not finalize the Chroma index. Re-run index.") from exc
        return total

    def retrieve(self, root, strategy, question, k):
        collection = self._get(collection_name(root, strategy))
        if collection is None:
            raise RagError(f"Empty index for {strategy}; run index with the same strategy first.")
        metadata = collection.metadata or {}
        if metadata.get("state") != "ready":
            raise RagError(f"The {strategy} index is incomplete; run index again.")
        if any(metadata.get(key) != value for key, value in self._signature().items()):
            raise RagError("The index schema or embedding model/revision changed; re-index.")
        try:
            count = collection.count()
        except Exception as exc:
            raise RagError("Could not count records in the local Chroma index.") from exc
        if not count:
            raise RagError(f"Empty index for {strategy}; no eligible text was indexed.")
        embedding = self.encode([question])
        try:
            result = collection.query(
                query_embeddings=embedding, n_results=min(k, count),
                include=["documents", "metadatas", "distances"],
            )
            return [
                Hit(Chunk(text=text, **meta), float(distance))
                for text, meta, distance in zip(
                    result["documents"][0], result["metadatas"][0],
                    result["distances"][0], strict=True,
                )
            ]
        except Exception as exc:
            raise RagError("Could not query the local index. Check the model and try re-indexing.") from exc
