"""Two-tier book classification: rule-based keywords + ML zero-shot fallback.

Classification strategy:
  1. **Rule-based**: Scan title + author + text for predefined keywords.
     Each keyword match increments a score; if the best category scores >= 3
     it is accepted.  This is fast and requires no model loading.
  2. **ML zero-shot**: Encode the text and all category labels using
     sentence-transformers, then pick the label with the highest cosine
     similarity (threshold >= 0.3).  This handles books that don't match
     any keyword rules.
  3. **Fallback**: If neither method is confident, return "Uncategorized".

The ML model is shared as a class-level singleton to avoid reloading
the ~90 MB model for each classification.
"""

import logging
import re
import threading
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ─── Rule-based keyword categories ─────────────────────────────
# Nested dict structure: { Category: { Subcategory: [keywords...] } }
# Keywords are matched case-insensitively against the combined
# title + author + text string.

CATEGORY_RULES: Dict[str, Dict[str, list]] = {
    "Programming": {
        "Python": ["python", "django", "flask", "pandas", "numpy", "pytorch"],
        "JavaScript": ["javascript", "typescript", "react", "vue", "angular", "node.js", "nodejs"],
        "Java": ["java ", " java", "spring", "maven", "gradle", "jvm"],
        "C/C++": ["c programming", "c++", "cpp", "stl ", "cmake", "embedded c"],
        "Rust": ["rust programming", "rustlang", "cargo ", "tokio"],
        "Go": ["golang", "go programming"],
        "Web Development": ["html", "css", "web development", "frontend", "backend", "fullstack"],
        "Mobile": ["android", "ios development", "swift", "kotlin", "flutter", "react native"],
        "DevOps": ["docker", "kubernetes", "ci/cd", "devops", "terraform", "ansible"],
        "General": ["programming", "software engineering", "algorithms", "data structures", "design patterns", "clean code"],
    },
    "Data Science": {
        "Machine Learning": ["machine learning", "deep learning", "neural network", "tensorflow", "keras"],
        "Data Analysis": ["data analysis", "data visualization", "matplotlib", "tableau"],
        "Statistics": ["statistics", "probability", "bayesian", "regression"],
        "NLP": ["natural language processing", "nlp", "text mining", "sentiment analysis"],
        "Computer Vision": ["computer vision", "image processing", "opencv"],
    },
    "Artificial Intelligence": {
        "General AI": ["artificial intelligence", " ai ", "intelligent systems"],
        "Deep Learning": ["deep learning", "convolutional", "recurrent", "transformer", "attention mechanism"],
        "Reinforcement Learning": ["reinforcement learning", "q-learning", "policy gradient"],
        "LLM": ["large language model", "llm", "gpt", "chatgpt", "prompt engineering"],
    },
    "Database": {
        "SQL": ["sql", "mysql", "postgresql", "sqlite", "oracle database"],
        "NoSQL": ["nosql", "mongodb", "redis", "cassandra", "elasticsearch"],
        "Data Engineering": ["data warehouse", "etl", "data pipeline", "spark", "hadoop"],
    },
    "System & Network": {
        "Operating Systems": ["operating system", "linux", "unix", "windows server"],
        "Networking": ["networking", "tcp/ip", "http", "dns", "network protocol"],
        "Security": ["cybersecurity", "security", "encryption", "penetration testing", "ethical hacking"],
        "Cloud": ["cloud computing", "aws", "azure", "gcp", "google cloud"],
    },
    "Mathematics": {
        "Linear Algebra": ["linear algebra", "matrix", "vector space", "eigenvalue"],
        "Calculus": ["calculus", "differential", "integral"],
        "Discrete Mathematics": ["discrete math", "graph theory", "combinatorics"],
        "Optimization": ["optimization", "linear programming", "convex"],
    },
    "Science": {
        "Physics": ["physics", "quantum", "thermodynamics", "mechanics"],
        "Chemistry": ["chemistry", "organic chemistry", "biochemistry"],
        "Biology": ["biology", "genetics", "molecular biology", "neuroscience"],
    },
    "Business": {
        "Management": ["management", "leadership", "organizational"],
        "Finance": ["finance", "investment", "accounting", "trading"],
        "Marketing": ["marketing", "branding", "advertising", "seo"],
        "Entrepreneurship": ["startup", "entrepreneurship", "business plan"],
    },
    "Literature": {
        "Fiction": ["novel", "fiction", "short stories"],
        "Non-Fiction": ["biography", "memoir", "essay"],
        "Philosophy": ["philosophy", "ethics", "logic", "metaphysics"],
        "History": ["history", "civilization", "ancient", "medieval"],
    },
}

# Flatten the nested category structure into "Category / Subcategory" strings
# for use as candidate labels in zero-shot ML classification.
ML_CATEGORIES = []
for cat, subcats in CATEGORY_RULES.items():
    for subcat in subcats:
        ML_CATEGORIES.append(f"{cat} / {subcat}")


class Classifier:
    """Two-tier book classifier: rules first, ML zero-shot fallback.

    Thread-safe: the sentence-transformers model is lazily loaded once
    and shared across all Classifier instances and threads.
    """

    _shared_model = None           # Shared sentence-transformers model (lazy-loaded)
    _model_load_failed = False     # Skip retries if model loading failed once
    _load_lock = threading.Lock()  # Thread-safe initialisation guard

    def _rule_classify(self, text: str) -> Optional[Dict[str, str]]:
        """Attempt classification using keyword frequency scoring.

        Counts occurrences of each subcategory's keywords in the text
        (case-insensitive, capped at 5 per keyword to prevent bias).
        Accepts the best match only if its total score >= 3.
        """
        text_lower = text.lower()

        best_match = None
        best_score = 0

        for category, subcategories in CATEGORY_RULES.items():
            for subcategory, keywords in subcategories.items():
                score = 0
                for kw in keywords:
                    count = len(re.findall(re.escape(kw), text_lower))
                    score += min(count, 5)

                if score > best_score:
                    best_score = score
                    best_match = {
                        "category": category,
                        "subcategory": subcategory,
                    }

        if best_score >= 3:
            return best_match
        return None

    def _ml_classify(self, text: str) -> Optional[Dict[str, str]]:
        """Classify using sentence-transformers zero-shot cosine similarity.

        Encodes the first 1000 chars of text and all ML_CATEGORIES labels,
        then finds the label with the highest cosine similarity.  Returns
        None if the best similarity is below 0.3 (not confident enough).
        """
        # Skip if model loading already failed in this process
        if Classifier._model_load_failed:
            return None

        try:
            if Classifier._shared_model is None:
                with Classifier._load_lock:
                    # Double-check inside lock
                    if Classifier._shared_model is None:
                        from sentence_transformers import SentenceTransformer
                        from config import settings
                        logger.info("Loading embedding model for classification...")
                        Classifier._shared_model = SentenceTransformer(settings.embedding_model)
                        logger.info("Classification model loaded successfully")

            from sentence_transformers import util

            text_embedding = Classifier._shared_model.encode(text[:1000], convert_to_tensor=True)
            label_embeddings = Classifier._shared_model.encode(ML_CATEGORIES, convert_to_tensor=True)

            similarities = util.cos_sim(text_embedding, label_embeddings)[0]

            best_idx = similarities.argmax().item()
            best_score = similarities[best_idx].item()

            if best_score < 0.3:
                return None

            best_label = ML_CATEGORIES[best_idx]
            parts = best_label.split(" / ")

            return {
                "category": parts[0],
                "subcategory": parts[1] if len(parts) > 1 else None,
                "confidence": best_score,
            }

        except Exception as e:
            logger.warning("ML classification failed (disabling for this session): %s", e)
            Classifier._model_load_failed = True
            return None

    def classify(
        self,
        title: str = "",
        text: str = "",
        author: str = "",
    ) -> Dict[str, str]:
        """Classify a book into a category and subcategory.

        Args:
            title: Book title.
            text: First ~5000 chars of extracted text content.
            author: Author name.

        Returns:
            Dict with "category" and "subcategory" keys.
            Falls back to {"category": "Uncategorized", "subcategory": None}.
        """
        combined = f"{title} {author} {text}"

        # Try rules first (instantaneous, no model needed)
        result = self._rule_classify(combined)
        if result:
            logger.info("Rule-classified: %s → %s/%s", title[:50], result["category"], result["subcategory"])
            return result

        # ML fallback
        result = self._ml_classify(combined)
        if result:
            logger.info(
                "ML-classified: %s → %s/%s (%.2f)",
                title[:50], result["category"], result.get("subcategory", ""),
                result.get("confidence", 0),
            )
            return result

        return {"category": "Uncategorized", "subcategory": None}
