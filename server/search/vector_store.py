"""FAISS vector store for semantic search."""

import asyncio
import logging
from typing import List, Optional, Tuple

import numpy as np

from config import settings

logger = logging.getLogger(__name__)

# Save index to disk after this many additions (reduces I/O dramatically)
_SAVE_EVERY = 500


class VectorStore:
    """FAISS-based vector store for semantic book search.

    Uses IndexHNSWFlat for fast approximate nearest-neighbour search,
    which scales well to hundreds of thousands of vectors without the
    brute-force O(n) cost of IndexFlatIP.
    """

    def __init__(self):
        self._model = None
        self._model_load_failed = False
        self._index = None
        self._id_map: dict = {}      # vector_idx -> book_id
        self._next_id: int = 0
        self._additions_since_save: int = 0
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
        """Get or create the FAISS index (HNSW for fast ANN search)."""
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
                logger.info(
                    "Creating new FAISS HNSW index (dim=%d)", settings.embedding_dimension
                )
                # HNSW: fast approximate search, no training required,
                # scales to millions of vectors with ~10ms query latency.
                # M=32 is a good balance of speed/accuracy/memory.
                self._index = faiss.IndexHNSWFlat(settings.embedding_dimension, 32)
                self._index.hnsw.efConstruction = 200  # Higher = better quality graph
                self._index.hnsw.efSearch = 64         # Higher = better recall at query time
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
        self._additions_since_save = 0

    def _encode_batch(self, texts: List[str]) -> Optional[np.ndarray]:
        """Encode a batch of texts to normalised embedding vectors."""
        model = self._get_model()
        if model is None:
            return None
        embeddings = model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=settings.batch_size,
            show_progress_bar=False,
        )
        return embeddings.astype("float32")

    def _encode(self, text: str) -> Optional[np.ndarray]:
        """Encode a single text to a normalised embedding vector."""
        result = self._encode_batch([text])
        if result is None:
            return None
        return result[0:1]

    async def add_texts(self, texts: List[str], book_ids: List[int]) -> List[Optional[int]]:
        """Add multiple texts to the vector store in one batch. Returns list of vector IDs."""
        if self._model_load_failed or not texts:
            return [None] * len(texts)

        try:
            loop = asyncio.get_running_loop()
            vectors = await loop.run_in_executor(None, self._encode_batch, texts)

            if vectors is None:
                return [None] * len(texts)

            index = self._get_index()
            start_id = self._next_id
            index.add(vectors)

            vector_ids = []
            for i, book_id in enumerate(book_ids):
                vid = start_id + i
                self._id_map[vid] = book_id
                vector_ids.append(vid)
            self._next_id += len(texts)
            self._additions_since_save += len(texts)

            if self._additions_since_save >= _SAVE_EVERY:
                await loop.run_in_executor(None, self._save_index)

            return vector_ids

        except Exception as e:
            logger.error("Failed to add vectors: %s", e)
            return [None] * len(texts)

    async def add_text(self, text: str, book_id: int) -> Optional[int]:
        """Add a single text entry to the vector store."""
        ids = await self.add_texts([text], [book_id])
        return ids[0]

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

        self._index = faiss.IndexHNSWFlat(settings.embedding_dimension, 32)
        self._index.hnsw.efConstruction = 200
        self._index.hnsw.efSearch = 64
        self._id_map = {}
        self._next_id = 0
        self._additions_since_save = 0

        model = self._get_model()
        if model is None:
            logger.warning("Cannot rebuild index: model not available")
            return

        texts = [t for t, _ in texts_and_ids]
        ids = [i for _, i in texts_and_ids]

        for batch_start in range(0, len(texts), settings.batch_size):
            batch_texts = texts[batch_start: batch_start + settings.batch_size]
            batch_ids = ids[batch_start: batch_start + settings.batch_size]

            embeddings = model.encode(
                batch_texts,
                normalize_embeddings=True,
                batch_size=settings.batch_size,
                show_progress_bar=False,
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
