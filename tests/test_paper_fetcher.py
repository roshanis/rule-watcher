from paper_fetcher import select_paper


def test_select_paper_prefers_recent_relevant_entry():
    candidates = [
        {
            "id": "old",
            "title": "Legacy study",
            "summary": "This paper discusses basic methods.",
            "published": "2024-01-01",
            "authors": ["A"],
            "link": "https://example.com/old",
            "categories": [],
        },
        {
            "id": "new",
            "title": "Transformer models for healthcare",
            "summary": "We explore transformer architectures in medical datasets.",
            "published": "2025-10-01",
            "authors": ["B"],
            "link": "https://example.com/new",
            "categories": [{"term": "cs.LG"}],
        },
    ]

    best = select_paper(candidates, ["transformer", "healthcare"])

    assert best["id"] == "new"
