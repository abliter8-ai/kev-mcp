"""Private, immutable SQLite document storage."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


class DocumentStore:
    def __init__(self, path: Path, max_bytes: int = 2_000_000):
        self.path = Path(path)
        self.max_bytes = max_bytes
        parent_existed = self.path.parent.exists()
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not parent_existed:
            os.chmod(self.path.parent, 0o700)
        self.path.touch(mode=0o600, exist_ok=True)
        os.chmod(self.path, 0o600)
        with closing(self._connect()) as db:
            with db:
                db.execute("""CREATE TABLE IF NOT EXISTS documents (
                document_id TEXT PRIMARY KEY, sha256 TEXT NOT NULL,
                text_bytes INTEGER NOT NULL, line_count INTEGER NOT NULL,
                created_at TEXT NOT NULL, title TEXT, source_url TEXT,
                fetched_at TEXT, text TEXT NOT NULL
                )""")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _metadata(row: sqlite3.Row) -> dict:
        return {key: row[key] for key in row.keys() if key != "text"}

    @staticmethod
    def _lines(text: str) -> int:
        return len(text.splitlines())

    def store(
        self,
        text: str,
        title: str | None = None,
        source_url: str | None = None,
        fetched_at: str | None = None,
    ) -> dict:
        if not text.strip():
            raise ValueError("document text is empty")
        text_bytes = len(text.encode("utf-8"))
        if text_bytes > self.max_bytes:
            raise ValueError(f"document exceeds max_bytes ({text_bytes} > {self.max_bytes})")
        metadata = {
            "document_id": str(uuid.uuid4()),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "text_bytes": text_bytes,
            "line_count": self._lines(text),
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "title": title,
            "source_url": source_url,
            "fetched_at": fetched_at,
        }
        with closing(self._connect()) as db:
            with db:
                db.execute(
                    "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (*metadata.values(), text),
                )
        return metadata

    def get(self, document_id: str) -> dict:
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT * FROM documents WHERE document_id = ?", (document_id,)
            ).fetchone()
        if row is None:
            raise ValueError(f"document not found: {document_id}")
        result = self._metadata(row)
        result["text"] = row["text"]
        return result

    def select(
        self, document_id: str, start_line: int | None = None, end_line: int | None = None
    ) -> dict:
        document = self.get(document_id)
        total = document["line_count"]
        if start_line is None and end_line is None:
            return {
                "document": {k: v for k, v in document.items() if k != "text"},
                "text": document["text"],
                "coverage": {
                    "kind": "full",
                    "start_line": 1,
                    "end_line": total,
                    "total_lines": total,
                },
            }
        start = 1 if start_line is None else start_line
        end = total if end_line is None else end_line
        if start < 1 or end < start or end > total:
            raise ValueError("line range is outside the document")
        chunks = document["text"].splitlines(keepends=True)
        selected = "".join(chunks[start - 1 : end])
        return {
            "document": {k: v for k, v in document.items() if k != "text"},
            "text": selected,
            "coverage": {
                "kind": "partial",
                "start_line": start,
                "end_line": end,
                "total_lines": total,
            },
        }

    def read(
        self,
        document_id: str,
        start_line: int | None = None,
        end_line: int | None = None,
        max_chars: int = 16000,
    ) -> dict:
        result = self.select(document_id, start_line, end_line)
        if len(result["text"]) > max_chars:
            raise ValueError(
                f"selected text exceeds max_chars ({len(result['text'])} > {max_chars})"
            )
        return result
