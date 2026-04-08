"""FAISS vector store for semantic search.

Provides the semantic search half of BookBrain's dual-engine search.
Text chunks are encoded into 384-dimensional vectors using sentence-transformers
and indexed in a FAISS HNSW (Hierarchical Navigable Small World) graph for
fast approximate nearest-neighbour retrieval.

Key features:
  - Lazy model loading (sentence-transformers loaded on first encode)
  - Incremental vector addition with periodic auto-save to disk
  - Bulk rebuild from scratch (for index corruption recovery)
  - Self-healing: reconciles the in-memory vector→chunk ID mapping with the DB
  - Thread-safe model sharing across ingest workers

Persistence:
  - ``data/index/faiss.index`` — the FAISS HNSW index binary
  - ``data/index/id_map.npy``  — numpy array mapping vector positions → chunk IDs
"""

import asyncio
import logging
import threading
from typing import List, Optional, Tuple

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Chunk

from config import settings

logger = logging.getLogger(__name__)

# Flush the FAISS index to disk after this many vector additions.
# Reduces I/O while ensuring data isn't lost if the process crashes.
_SAVE_EVERY = 500


class VectorStore:
    """FAISS-based vector store for semantic book search.

    Uses IndexHNSWFlat for fast approximate nearest-neighbour search,
    which scales to hundreds of thousands of vectors with sub-linear
    query time (vs. brute-force O(n) with IndexFlatIP).

    The ``_id_map`` array translates FAISS internal vector positions to
    application-level chunk IDs.  This indirection is needed because FAISS
    doesn't natively support arbitrary integer IDs with HNSW indexes.
    """

    _shared_model = None           # Shared sentence-transformers model
    _model_load_failed = False     # Skip retries if loading failed once
    _load_lock = threading.Lock()  # Thread-safe model initialisation

    def __init__(self):
        self._index = None                                          # FAISS index (lazy-loaded)
        self._id_map: np.ndarray = np.array([], dtype=np.int64)     # Maps vector position → chunk ID
        self._next_id: int = 0                                      # Next expected vector count
        self._additions_since_save: int = 0                         # Pending saves counter
        self._index_path = settings.index_dir / "faiss.index"       # FAISS index file path
        self._map_path = settings.index_dir / "id_map.npy"          # ID mapping file path

    def _get_model(self):
        """Lazy-load the sentence-transformer model."""
        if VectorStore._model_load_failed:
            return None
        if VectorStore._shared_model is None:
            with VectorStore._load_lock:
                if VectorStore._shared_model is None:
                    try:
                        from sentence_transformers import SentenceTransformer
                        logger.info("Loading embedding model: %s", settings.embedding_model)
                        VectorStore._shared_model = SentenceTransformer(settings.embedding_model)
                        logger.info("Model loaded successfully")
                    except Exception as e:
                        logger.warning("Failed to load embedding model (disabling vector search): %s", e)
                        VectorStore._model_load_failed = True
                        return None
        return VectorStore._shared_model

    def _get_index(self):
        """Get or create the FAISS HNSW index.

        On first call, tries to load an existing index from disk.  If no
        index file exists, creates a new one with HNSW parameters tuned for
        a balance of speed and recall (M=32, efConstruction=200, efSearch=64).
        Also handles backward-compatible migration from the old dict-based
        id_map format to the current numpy array format.
        """
        if self._index is None:
            import faiss

            if self._index_path.exists():
                logger.info("Loading existing FAISS index from %s", self._index_path)
                self._index = faiss.read_index(str(self._index_path))
                if self._map_path.exists():
                    try:
                        data = np.load(str(self._map_path), allow_pickle=True)
                        
                        # Handle backward compatibility (migration from dict to array)
                        if isinstance(data, np.ndarray):
                            # New format: raw array of IDs
                            self._id_map = data
                            self._next_id = len(data)
                        else:
                            # Old format: pickled dictionary
                            logger.info("Migrating old id_map dictionary to array format...")
                            map_dict = data.item().get("id_map", {})
                            self._next_id = data.item().get("next_id", 0)
                            
                            # Convert dict to array (fill missing with -1)
                            new_map = np.full(self._next_id, -1, dtype=np.int64)
                            for k, v in map_dict.items():
                                if int(k) < self._next_id:
                                    new_map[int(k)] = v
                            self._id_map = new_map
                            
                    except Exception as e:
                        logger.warning("Failed to load id_map: %s", e)
                        self._id_map = np.array([], dtype=np.int64)
                        self._next_id = 0
            else:
                logger.info(
                    "Creating new FAISS HNSW index (dim=%d)", settings.embedding_dimension
                )
                self._index = faiss.IndexHNSWFlat(settings.embedding_dimension, 32)
                self._index.hnsw.efConstruction = 200
                self._index.hnsw.efSearch = 64
                self._id_map = np.array([], dtype=np.int64)
                self._next_id = 0

        return self._index

    def _save_index(self):
        """Persist FAISS index and ID map to disk."""
        import faiss

        settings.index_dir.mkdir(parents=True, exist_ok=True)
        if self._index is not None:
            faiss.write_index(self._index, str(self._index_path))
            # Save raw array for maximum performance
            np.save(str(self._map_path), self._id_map)
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

    async def add_texts(self, texts: List[str], object_ids: List[int]) -> List[Optional[int]]:
        """Encode and add multiple texts to the vector store in one batch.

        Encoding runs in a thread executor to avoid blocking the event loop.
        The FAISS index is auto-saved to disk every ``_SAVE_EVERY`` additions.

        Args:
            texts: List of text strings to encode.
            object_ids: Corresponding chunk IDs (same length as texts).

        Returns:
            List of assigned vector IDs (or None for failed entries).
        """
        if self._model_load_failed or not texts:
            return [None] * len(texts)

        try:
            loop = asyncio.get_running_loop()
            vectors = await loop.run_in_executor(None, self._encode_batch, texts)

            if vectors is None:
                return [None] * len(texts)

            index = self._get_index()
            start_id = index.ntotal # Use current total as offset for new additions
            index.add(vectors)

            # Bulk append to the mapping array
            new_ids = np.array(object_ids, dtype=np.int64)
            if self._id_map.size == 0:
                self._id_map = new_ids
            else:
                self._id_map = np.concatenate([self._id_map, new_ids])
            
            self._next_id = index.ntotal
            self._additions_since_save += len(texts)

            if self._additions_since_save >= _SAVE_EVERY:
                await loop.run_in_executor(None, self._save_index)

            # Return the vector IDs (contiguous range starting from start_id)
            return list(range(start_id, self._next_id))

        except Exception as e:
            logger.error("Failed to add vectors: %s", e)
            return [None] * len(texts)

    async def add_text(self, text: str, object_id: int) -> Optional[int]:
        """Add a single text entry to the vector store."""
        ids = await self.add_texts([text], [object_id])
        return ids[0]

    async def search(
        self, query: str, top_k: int = 20
    ) -> List[Tuple[int, float]]:
        """Search for semantically similar chunks.

        Encodes the query text, searches the FAISS index for the top-k
        nearest neighbours, and converts L2 distances to 0.0–1.0 similarity
        scores (1.0 = perfect match).

        Returns:
            List of (chunk_id, similarity_score) tuples, sorted by relevance.
        """
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
                idx_int = int(idx)
                if 0 <= idx_int < len(self._id_map):
                    obj_id = self._id_map[idx_int]
                    if obj_id != -1:
                        # Convert L2 distance to a 0.0-1.0 similarity score
                        # (1.0 = perfect match, lower = less similar)
                        similarity = 1.0 / (1.0 + float(score))
                        results.append((int(obj_id), similarity))

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
        self._id_map = np.array([], dtype=np.int64)
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

    async def heal_index(self, session: AsyncSession):
        """Repair the vector→chunk ID mapping by reconstructing it from the database.

        Queries all chunks that have a ``vector_id`` set, then rebuilds the
        ``_id_map`` array so that each FAISS vector position correctly maps
        to its chunk ID.  This recovers from crashes or interrupted ingests
        that left the mapping out of sync.

        Called automatically during application startup as a background task.
        """
        logger.info("Starting search index self-healing...")
        
        # Get all chunks that have a vector_id
        result = await session.execute(
            select(Chunk.vector_id, Chunk.id)
            .where(Chunk.vector_id.isnot(None))
            .order_by(Chunk.vector_id.asc())
        )
        rows = result.all()
        if not rows:
            logger.info("No vectors found in database to heal mapping.")
            return

        max_vid = max(row[0] for row in rows)
        logger.info("Healing mapping for up to %d vectors", max_vid + 1)
        
        # Build new map array (initialize with -1)
        new_map = np.full(max_vid + 1, -1, dtype=np.int64)
        for vid, cid in rows:
            if vid < len(new_map):
                new_map[vid] = cid
        
        self._id_map = new_map
        self._next_id = len(new_map)
        self._save_index()
        logger.info("Search index mapping healed successfully.")


# Singleton vector store instance used throughout the application
vector_store = VectorStore()
