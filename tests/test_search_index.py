from search_index import rank


def test_rank_prioritizes_relevant_documents():
    documents = [
        {
            "id": "doc1",
            "title": "Transformer models enhance healthcare analytics",
            "summary": "We apply transformers to predict health outcomes.",
            "url": "https://example.com/doc1",
            "published": "2025-10-01",
            "source": "ai",
        },
        {
            "id": "doc2",
            "title": "Unrelated topic",
            "summary": "A paper about unrelated subject matter.",
            "url": "https://example.com/doc2",
            "published": "2025-09-15",
            "source": "govt",
        },
    ]

    results = rank("healthcare transformer", documents, limit=2)

    assert results[0]["id"] == "doc1"
    assert results[0]["score"] >= results[1]["score"]
