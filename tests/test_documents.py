from pathlib import Path

import pytest

from kev_mcp.documents import DocumentStore


def test_store_get_persists_metadata_and_exact_text(tmp_path: Path):
    text = "first\nsecond\n"
    store = DocumentStore(tmp_path / "documents.sqlite3")

    metadata = store.store(text, title="Example", source_url="https://example.test/a")

    assert set(metadata) == {
        "document_id",
        "sha256",
        "text_bytes",
        "line_count",
        "created_at",
        "title",
        "source_url",
        "fetched_at",
    }
    assert metadata["text_bytes"] == len(text.encode())
    assert metadata["line_count"] == 2
    assert store.get(metadata["document_id"]) == {**metadata, "text": text}

    reopened = DocumentStore(tmp_path / "documents.sqlite3")
    assert reopened.get(metadata["document_id"])["text"] == text


def test_store_rejects_over_limit_and_missing_id(tmp_path: Path):
    store = DocumentStore(tmp_path / "documents.sqlite3", max_bytes=3)
    with pytest.raises(ValueError, match="max_bytes"):
        store.store("four")
    with pytest.raises(ValueError, match="not found"):
        store.get("missing")


def test_select_and_read_report_precise_partial_coverage(tmp_path: Path):
    store = DocumentStore(tmp_path / "documents.sqlite3")
    metadata = store.store("a\nb\nc\n")

    full = store.select(metadata["document_id"])
    assert full["text"] == "a\nb\nc\n"
    assert full["coverage"] == {"kind": "full", "start_line": 1, "end_line": 3, "total_lines": 3}

    partial = store.read(metadata["document_id"], start_line=2, end_line=3)
    assert partial["text"] == "b\nc\n"
    assert partial["coverage"] == {
        "kind": "partial",
        "start_line": 2,
        "end_line": 3,
        "total_lines": 3,
    }

    with pytest.raises(ValueError, match="max_chars"):
        store.read(metadata["document_id"], max_chars=2)
    with pytest.raises(ValueError, match="line"):
        store.select(metadata["document_id"], start_line=0)


def test_line_count_and_ranges_follow_python_line_separators(tmp_path: Path):
    store = DocumentStore(tmp_path / "documents.sqlite3")
    metadata = store.store("one\rtwo\u2028three")

    assert metadata["line_count"] == 3
    assert store.select(metadata["document_id"], start_line=2, end_line=2)["text"] == "two\u2028"


def test_whitespace_only_documents_are_rejected(tmp_path: Path):
    store = DocumentStore(tmp_path / "documents.sqlite3")
    with pytest.raises(ValueError, match="empty"):
        store.store(" \n\t")


def test_document_ids_are_isolated_between_stores(tmp_path: Path):
    first = DocumentStore(tmp_path / "one.sqlite3")
    second = DocumentStore(tmp_path / "two.sqlite3")
    document_id = first.store("private")["document_id"]

    with pytest.raises(ValueError, match="not found"):
        second.get(document_id)
