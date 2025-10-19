"""Ranking helpers using BM25 and cosine similarity."""

from __future__ import annotations

import logging
from typing import Dict, List

import numpy as np

logger = logging.getLogger(__name__)

try:
    from rank_bm25 import BM25Okapi  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    BM25Okapi = None
    logger.warning("rank_bm25 not available; BM25 scores disabled")

try:
    from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
    from sklearn.metrics.pairwise import cosine_similarity  # type: ignore
except Exception:  # pragma: no cover
    TfidfVectorizer = None
    cosine_similarity = None
    logger.warning("scikit-learn not available; cosine similarity disabled")


def tokenize(text: str) -> List[str]:
    return [token for token in text.lower().split() if token]


def compute_scores(query: str, corpus: List[str]) -> Dict[str, np.ndarray]:
    tokens = [tokenize(text) for text in corpus]
    query_tokens = tokenize(query)

    bm25_scores = np.zeros(len(corpus))
    if BM25Okapi and tokens:
        try:
            bm25 = BM25Okapi(tokens)
            bm25_scores = np.array(bm25.get_scores(query_tokens))
        except Exception as exc:
            logger.warning("BM25 scoring failed: %s", exc)

    cosine_scores = np.zeros(len(corpus))
    if TfidfVectorizer and cosine_similarity:
        try:
            tfidf = TfidfVectorizer(stop_words="english")
            matrix = tfidf.fit_transform(corpus + [query])
            cosine = cosine_similarity(matrix[-1], matrix[:-1])
            cosine_scores = cosine.flatten()
        except Exception as exc:
            logger.warning("Cosine similarity failed: %s", exc)

    return {"bm25": bm25_scores, "cosine": cosine_scores}


def rank(query: str, documents: List[Dict], limit: int = 20) -> List[Dict]:
    if not documents:
        return []

    corpus = [f"{doc.get('title', '')}\n{doc.get('summary', '')}" for doc in documents]
    scores = compute_scores(query, corpus)

    bm25_scores = scores["bm25"]
    cosine_scores = scores["cosine"]

    bm25_norm = bm25_scores / bm25_scores.max() if bm25_scores.max() > 0 else bm25_scores
    cosine_norm = cosine_scores / cosine_scores.max() if cosine_scores.max() > 0 else cosine_scores

    combined = 0.6 * bm25_norm + 0.4 * cosine_norm

    ranked = []
    for doc, final_score, b_score, c_score in zip(documents, combined, bm25_scores, cosine_scores):
        enriched = dict(doc)
        enriched.update(
            {
                "score": float(final_score),
                "bm25": float(b_score),
                "cosine": float(c_score),
            }
        )
        ranked.append(enriched)

    ranked.sort(key=lambda d: d["score"], reverse=True)
    return ranked[:limit]
