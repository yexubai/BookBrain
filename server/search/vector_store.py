"""FAISS vector store for semantic search."""

import asyncio
import logging
from typing import List, Optional, Tuple

import numpy as np

from config import settings

logger = logging.getLogger(__name__)


class VectorStore:
    """FAISS-based vector store for semantic book search."""

    def __init__(self):
        self._model = None
        self._model_load_failed = False  # Don't retry if loading failed
        self._index = None
        self._id_map: dict = {}  # vector_idx -> book_id
        self._next_id: int = 0
        self._index_path = settings.index_dir / "faiss.index"
        self._map_path = settings.index_dir / "id_map.npy"

    def _get_model(self):
        """Lazy-load the sentence-transformer model."""
        if self._model_load_failed:
            return None

        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info("Loading embedding model: %s", settings.embedding_model)
                self._model = SentenceTransformer(settings.embedding_model)
                logger.info("Model loaded successfully")
            except Exception as e:
                logger.warning("Failed to load embedding model (disabling vector search): %s", e)
                self._model_load_failed = True
                return None

        return self._model

    def _get_index(self):
        """Get or create the FAISS index."""
        if self._index is None:
            import faiss

            if self._index_path.exists():
                logger.info("Loading existing FAISS index from %s", self._index_path)
                self._index = faiss.read_index(str(self._index_path))
                if self._map_path.exists():
                    data = np.load(str(self._map_path), allow_pickle=True).item()
                    self._id_map = data.get("id_map", {})
                    self._next_id = data.get("next_id", 0)
            else:
                logger.info("Creating new FAISS index (dim=%d)", settings.embedding_dimension)
                self._index = faiss.IndexFlatIP(settings.embedding_dimension)
                self._id_map = {}
                self._next_id = 0

        return self._index

    def _save_index(self):
        """Persist FAISS index and ID map to disk."""
        import faiss

        settings.index_dir.mkdir(parents=True, exist_ok=True)

        if self._index is not None:
            faiss.write_index(self._index, str(self._index_path))
            np.save(
                str(self._map_path),
                {"id_map": self._id_map, "next_id": self._next_id},
            )
            logger.info("FAISS index saved (%d vectors)", self._index.ntotal)

    def _encode(self, text: str) -> Optional[np.ndarray]:
        """Encode text to a normalized embedding vector."""
        model = self._get_model()
        if model is None:
            return None
        embedding = model.encode(text, normalize_embeddings=True)
        return embedding.reshape(1, -1).astype("float32")

    async def add_text(self, text: str, book_id: int) -> Optional[int]:
        """Add a text entry to the vector store."""
        if self._model_load_failed:
            return None

        try:
            loop = asyncio.get_running_loop()
            vector = await loop.run_in_executor(None, self._encode, text)

            if vector is None:
                return None

            index = self._get_index()
            vector_id = self._next_id
            index.add(vector)
            self._id_map[vector_id] = book_id
            self._next_id += 1

            # Save periodically
            if self._next_id % 10 == 0:
                await loop.run_in_executor(None, self._save_index)

            return vector_id

        except Exception as e:
            logger.error("Failed to add vector for book %d: %s", book_id, e)
            return None

    async def search(
        self, query: str, top_k: int = 20
    ) -> List[Tuple[int, float]]:
        """Search for similar documents. Returns list of (book_id, score)."""
        if self._model_load_failed:
            return []

        try:
            index = self._get_index()
            if index.ntotal == 0:
                return []

            loop = asyncio.get_running_loop()
            query_vector = await loop.run_in_executor(None, self._encode, query)

            if query_vector is None:
                return []

            k = min(top_k, index.ntotal)
            scores, indices = index.search(query_vector, k)

            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx == -1:
                    continue
                book_id = self._id_map.get(int(idx))
                if book_id is not None:
                    results.append((book_id, float(score)))

            return results

        except Exception as e:
            logger.error("Vector search failed: %s", e)
            return []

    async def save(self):
        """Force save the index to disk."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._save_index)

    async def rebuild(self, texts_and_ids: List[Tuple[str, int]]):
        """Rebuild the entire index from scratch."""
        import faiss

        logger.info("Rebuilding FAISS index with %d entries", len(texts_and_ids))

        self._index = faiss.IndexFlatIP(settings.embedding_dimension)
        self._id_map = {}
        self._next_id = 0

        model = self._get_model()
        if model is None:
            logger.warning("Cannot rebuild index: model not available")
            return

        texts = [t for t, _ in texts_and_ids]
        ids = [i for _, i in texts_and_ids]

        for batch_start in range(0, len(texts), settings.batch_size):
            batch_texts = texts[batch_start : batch_start + settings.batch_size]
            batch_ids = ids[batch_start : batch_start + settings.batch_size]

            embeddings = model.encode(
                batch_texts, normalize_embeddings=True, batch_size=settings.batch_size
            )
            embeddings = embeddings.astype("float32")

            self._index.add(embeddings)

            for book_id in batch_ids:
                self._id_map[self._next_id] = book_id
                self._next_id += 1

        self._save_index()
        logger.info("Index rebuilt: %d vectors", self._index.ntotal)


# Global vector store instance
vector_store = VectorStore()
