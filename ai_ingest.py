"""Cron-friendly entry point to gather AI-related updates."""

import logging
from typing import List

from ai_fetchers import fetch_all
from ai_storage import save_items


def main(limit: int = 100) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logging.info("Starting AI ingest (limit=%s)", limit)
    items = fetch_all(limit=limit)
    logging.info("Fetched %s items", len(items))
    saved = save_items(items)
    logging.info("Saved %s items", saved)


if __name__ == "__main__":
    main()
