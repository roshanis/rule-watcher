"""Shared utilities."""

import re


def normalize_doc_id(raw: str) -> str:
    """Generate a storage-friendly identifier for voting/comment keys."""
    if not raw:
        return ""
    return re.sub(r"[^A-Za-z0-9_\-]", "-", raw)[:100]
