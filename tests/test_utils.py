from utils import normalize_doc_id


def test_normalize_doc_id_replaces_invalid_chars():
    raw = "abc/123:paper"
    assert normalize_doc_id(raw) == "abc-123-paper"


def test_normalize_doc_id_truncates_long_ids():
    raw = "x" * 150
    assert len(normalize_doc_id(raw)) == 100
