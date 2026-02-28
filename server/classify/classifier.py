"""Two-tier book classification: rule-based + ML zero-shot."""

import logging
import re
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ─── Rule-based keyword categories ──────────────────────────────

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

# Flatten for ML labels
ML_CATEGORIES = []
for cat, subcats in CATEGORY_RULES.items():
    for subcat in subcats:
        ML_CATEGORIES.append(f"{cat} / {subcat}")


class Classifier:
    """Two-tier book classifier: rules first, ML fallback."""

    def __init__(self):
        self._model = None

    def _rule_classify(self, text: str) -> Optional[Dict[str, str]]:
        """Try to classify using keyword rules.

        Returns dict with category/subcategory or None.
        """
        text_lower = text.lower()

        best_match = None
        best_score = 0

        for category, subcategories in CATEGORY_RULES.items():
            for subcategory, keywords in subcategories.items():
                score = 0
                for kw in keywords:
                    # Count occurrences (bounded)
                    count = len(re.findall(re.escape(kw), text_lower))
                    score += min(count, 5)  # Cap per keyword

                if score > best_score:
                    best_score = score
                    best_match = {
                        "category": category,
                        "subcategory": subcategory,
                    }

        # Require minimum score for rule-based
        if best_score >= 3:
            return best_match
        return None

    def _ml_classify(self, text: str) -> Optional[Dict[str, str]]:
        """Classify using sentence-transformers zero-shot approach.

        Computes similarity between text and category labels.
        """
        try:
            from sentence_transformers import SentenceTransformer, util
            from config import settings

            if self._model is None:
                logger.info("Loading embedding model for classification...")
                self._model = SentenceTransformer(settings.embedding_model)

            # Encode text and category labels
            text_embedding = self._model.encode(text[:1000], convert_to_tensor=True)
            label_embeddings = self._model.encode(ML_CATEGORIES, convert_to_tensor=True)

            # Compute cosine similarities
            similarities = util.cos_sim(text_embedding, label_embeddings)[0]

            # Get best match
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
            logger.warning("ML classification failed: %s", e)
            return None

    def classify(
        self,
        title: str = "",
        text: str = "",
        author: str = "",
    ) -> Dict[str, str]:
        """Classify a book using rules then ML fallback.

        Args:
            title: Book title.
            text: Book text content (first few thousand chars).
            author: Book author.

        Returns:
            Dict with 'category' and optionally 'subcategory'.
        """
        combined = f"{title} {author} {text}"

        # Try rules first (faster)
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

        # Default
        return {"category": "Uncategorized", "subcategory": None}
