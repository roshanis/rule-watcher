"""External sources for AI-related updates."""

from datetime import datetime
import json
from pathlib import Path
from typing import Dict, List

import logging

import requests

logger = logging.getLogger(__name__)

HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"


def _load_queries() -> List[str]:
    config_path = Path("config/ai_keywords.json")
    if not config_path.exists():
        return [
            "ai healthcare",
            '"health insurance" ai',
        ]
    try:
        data = json.loads(config_path.read_text())
        return list(dict.fromkeys(filter(None, data.get("hackernews_queries", [])))) or [
            "ai healthcare",
            '"health insurance" ai',
        ]
    except Exception as exc:
        logger.warning("Failed to load AI query config: %s", exc)
        return [
            "ai healthcare",
            '"health insurance" ai',
        ]


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def _normalize_timestamp(value: str) -> str:
    if not value:
        return None
    try:
        # Handle common ISO formats
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat(timespec="seconds")
    except ValueError:
        return None


def fetch_hackernews(limit: int = 100) -> List[Dict[str, str]]:
    fetched_at = _now()
    results: Dict[str, Dict[str, str]] = {}
    for query in _load_queries():
        try:
            resp = requests.get(
                HN_SEARCH_URL,
                params={
                    "query": query,
                    "tags": "story",
                    "hitsPerPage": limit,
                    "restrictSearchableAttributes": "title,story_text",
                },
                timeout=15,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("HackerNews fetch failed for query '%s': %s", query, exc)
            continue

        for hit in resp.json().get("hits", []):
            external_id = hit.get("objectID")
            title = hit.get("title") or hit.get("story_title")
            url = hit.get("url") or hit.get("story_url")
            if not external_id or not title or not url:
                continue
            key = f"hn_{external_id}"
            results[key] = {
                "source": "hackernews",
                "external_id": key,
                "title": title,
                "url": url,
                "published_at": _normalize_timestamp(hit.get("created_at")),
                "fetched_at": fetched_at,
            }

    return list(results.values())[:limit]


def fetch_all(limit: int = 100) -> List[Dict[str, str]]:
    combined: Dict[str, Dict[str, str]] = {}
    for item in fetch_hackernews(limit=limit):
        combined.setdefault(item["external_id"], item)

    items = list(combined.values())
    items.sort(key=lambda x: x.get("published_at") or x.get("fetched_at"), reverse=True)
    return items[:limit]
