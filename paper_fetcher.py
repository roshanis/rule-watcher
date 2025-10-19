"""Fetch and score arXiv papers for the paper-of-the-day page."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlencode

import feedparser

logger = logging.getLogger(__name__)


DEFAULT_CONFIG = {
    "search_queries": ["cat:cs.LG", "cat:cs.CL"],
    "keywords": ["transformer", "healthcare", "reinforcement learning", "medical", "graph", "privacy"],
    "max_results": 20,
}

ARXIV_API = "http://export.arxiv.org/api/query"


def load_config() -> Dict:
    config_path = Path("config/arxiv_config.json")
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text())
            return {**DEFAULT_CONFIG, **data}
        except Exception as exc:
            logger.warning("Failed to load arXiv config, using defaults: %s", exc)
    return DEFAULT_CONFIG


def build_query(config: Dict) -> str:
    queries = config.get("search_queries") or DEFAULT_CONFIG["search_queries"]
    # Combine queries with OR to widen the pool
    normalized = [q.strip() for q in queries if q.strip()]
    return " OR ".join(normalized) if normalized else "cat:cs.LG"


def fetch_candidates(max_results: int) -> List[Dict]:
    config = load_config()
    search_query = build_query(config)
    params = {
        "search_query": search_query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": max_results,
    }
    try:
        url = f"{ARXIV_API}?{urlencode(params)}"
        feed = feedparser.parse(url)
    except Exception as exc:
        logger.error("Failed to fetch arXiv feed: %s", exc)
        return []

    items: List[Dict] = []
    for entry in feed.entries[:max_results]:
        items.append(
            {
                "id": getattr(entry, "id", ""),
                "title": getattr(entry, "title", "(untitled)"),
                "summary": getattr(entry, "summary", ""),
                "published": getattr(entry, "published", ""),
                "authors": [a.name for a in getattr(entry, "authors", [])],
                "link": getattr(entry, "link", ""),
                "pdf_url": _extract_pdf(entry),
                "categories": getattr(entry, "tags", []),
            }
        )
    return items


def _extract_pdf(entry) -> str:
    for link in getattr(entry, "links", []):
        if link.get("type") == "application/pdf":
            return link.get("href")
    # Fallback to canonical link with "pdf"
    if hasattr(entry, "id"):
        return f"{entry.id}.pdf" if not entry.id.endswith(".pdf") else entry.id
    return ""


def score_item(item: Dict, keywords: List[str]) -> float:
    score = 0.0
    published = item.get("published")
    if published:
        try:
            dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            age_days = (datetime.utcnow() - dt).days
            score += max(0, 14 - age_days)  # recent papers get higher score
        except Exception:
            pass

    title = item.get("title", "").lower()
    summary = item.get("summary", "").lower()
    for kw in keywords:
        if kw.lower() in title:
            score += 5
        elif kw.lower() in summary:
            score += 2

    # Slight boost for healthcare / medic topics in categories
    categories = " ".join(tag.get("term", "") for tag in item.get("categories", []))
    if "med" in categories.lower():
        score += 3

    return score


def select_paper(candidates: List[Dict], keywords: List[str]) -> Dict:
    if not candidates:
        return {}
    scored = [(score_item(item, keywords), item) for item in candidates]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    best_score, best_item = scored[0]
    best_item["score"] = best_score
    return best_item


def get_paper_of_the_day() -> Dict:
    config = load_config()
    max_results = int(config.get("max_results", DEFAULT_CONFIG["max_results"]))
    candidates = fetch_candidates(max_results)
    paper = select_paper(candidates, config.get("keywords", []))
    return paper
