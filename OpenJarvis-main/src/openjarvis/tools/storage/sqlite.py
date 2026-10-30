"""SQLite/FTS5 memory backend — zero-dependency default."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from openjarvis.core.events import EventType, get_event_bus
from openjarvis.core.registry import MemoryRegistry
from openjarvis.tools.storage._stubs import (
    MemoryBackend,
    RetrievalResult,
)


def _check_fts5(conn: sqlite3.Connection) -> bool:
    """Return True if the SQLite build includes FTS5."""
    try:
        opts = conn.execute("PRAGMA compile_options").fetchall()
        return any("FTS5" in o[0].upper() for o in opts)
    except sqlite3.Error:
        return False


@MemoryRegistry.register("sqlite")
class SQLiteMemory(MemoryBackend):
    """Full-text search memory backend using SQLite FTS5.

    Uses the built-in ``sqlite3`` module — no extra dependencies.
    """

    backend_id: str = "sqlite"

    def __init__(self, db_path: str | Path = "") -> None:
        if not db_path:
            from openjarvis.core.config import DEFAULT_CONFIG_DIR

            db_path = str(DEFAULT_CONFIG_DIR / "memory.db")

        self._db_path = str(db_path)

        from openjarvis._rust_bridge import get_rust_module

        self._rust_impl = None
        self._conn: sqlite3.Connection | None = None
        try:
            _rust = get_rust_module()
            self._rust_impl = _rust.SQLiteMemory(self._db_path)
        except (ImportError, AttributeError, OSError):
            # Rust is an accelerator, not a prerequisite for the declared
            # SQLite backend. Keep local memory usable on a clean Windows
            # install where rustc/maturin has not been installed yet.
            self._conn = sqlite3.connect(self._db_path, timeout=10)
            self._conn.row_factory = sqlite3.Row
            self._create_python_tables()

    def _create_python_tables(self) -> None:
        if self._conn is None:
            return
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id       TEXT PRIMARY KEY,
                content  TEXT NOT NULL,
                source   TEXT NOT NULL DEFAULT '',
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at REAL NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
            USING fts5(
                content,
                source,
                tokenize='porter unicode61'
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts_python
            USING fts5(
                content,
                source,
                doc_id UNINDEXED,
                metadata UNINDEXED,
                tokenize='porter unicode61'
            );
        """)
        self._conn.commit()

    def store(
        self,
        content: str,
        *,
        source: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Persist *content* and return a unique document id."""
        meta_json = json.dumps(metadata) if metadata else None
        if self._rust_impl is not None:
            doc_id = self._rust_impl.store(content, source, meta_json)
        else:
            doc_id = str(uuid.uuid4())
            assert self._conn is not None
            self._conn.execute(
                "INSERT INTO documents(id, content, source, metadata, created_at) VALUES (?, ?, ?, ?, strftime('%s','now'))",
                (doc_id, content, source, meta_json or "{}"),
            )
            self._conn.execute(
                "INSERT INTO documents_fts_python(content, source, doc_id, metadata) VALUES (?, ?, ?, ?)",
                (content, source, doc_id, meta_json or "{}"),
            )
            self._conn.commit()
        bus = get_event_bus()
        bus.publish(
            EventType.MEMORY_STORE,
            {
                "backend": self.backend_id,
                "doc_id": doc_id,
                "source": source,
            },
        )
        return doc_id

    def replace_source(
        self,
        source: str,
        documents: List[tuple[str, Optional[Dict[str, Any]]]],
    ) -> List[str]:
        """Atomically replace all documents associated with *source*."""
        payload = [
            (content, json.dumps(metadata) if metadata else None)
            for content, metadata in documents
        ]
        if self._rust_impl is not None:
            doc_ids = self._rust_impl.replace_source(source, payload)
        else:
            assert self._conn is not None
            self._conn.execute("DELETE FROM documents WHERE source = ?", (source,))
            self._conn.execute("DELETE FROM documents_fts_python WHERE source = ?", (source,))
            doc_ids = []
            for content, meta_json in payload:
                doc_id = str(uuid.uuid4())
                doc_ids.append(doc_id)
                self._conn.execute(
                    "INSERT INTO documents(id, content, source, metadata, created_at) VALUES (?, ?, ?, ?, strftime('%s','now'))",
                    (doc_id, content, source, meta_json or "{}"),
                )
                self._conn.execute(
                    "INSERT INTO documents_fts_python(content, source, doc_id, metadata) VALUES (?, ?, ?, ?)",
                    (content, source, doc_id, meta_json or "{}"),
                )
            self._conn.commit()
        bus = get_event_bus()
        for doc_id in doc_ids:
            bus.publish(
                EventType.MEMORY_STORE,
                {
                    "backend": self.backend_id,
                    "doc_id": doc_id,
                    "source": source,
                },
            )
        return doc_ids

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        **kwargs: Any,
    ) -> List[RetrievalResult]:
        """Search via FTS5 MATCH with BM25 ranking — always via Rust backend."""
        if not query.strip():
            return []

        if self._rust_impl is not None:
            from openjarvis._rust_bridge import retrieval_results_from_json

            results = retrieval_results_from_json(self._rust_impl.retrieve(query, top_k))
        else:
            assert self._conn is not None
            # Build a safe FTS expression from natural-language terms. Raw
            # punctuation such as the apostrophe in "user's" is FTS syntax,
            # not user intent; quoting individual terms avoids false empty
            # results and MATCH parser errors.
            terms = re.findall(r"[\w]+", query, flags=re.UNICODE)
            fts_query = " OR ".join(f'"{term.replace(chr(34), "")}"' for term in terms)
            try:
                rows = self._conn.execute(
                    """SELECT doc_id, content, source, metadata, bm25(documents_fts_python) AS rank
                       FROM documents_fts_python WHERE documents_fts_python MATCH ?
                       ORDER BY rank LIMIT ?""",
                    (fts_query, top_k),
                ).fetchall()
            except sqlite3.OperationalError:
                # FTS5 MATCH treats punctuation as query syntax. A LIKE
                # fallback keeps natural-language queries such as "user's"
                # functional instead of returning a 500 or zero silently.
                where = " AND ".join("content LIKE ?" for _ in terms)
                rows = self._conn.execute(
                    f"SELECT id AS doc_id, content, source, metadata, 0 AS rank FROM documents WHERE {where} LIMIT ?",
                    [*(f"%{term}%" for term in terms), top_k],
                ).fetchall() if terms else []
            results = [
                RetrievalResult(
                    content=row["content"],
                    score=1.0 / (1.0 + abs(float(row["rank"]))),
                    source=row["source"],
                    metadata=json.loads(row["metadata"] or "{}"),
                )
                for row in rows
            ]
        bus = get_event_bus()
        bus.publish(
            EventType.MEMORY_RETRIEVE,
            {
                "backend": self.backend_id,
                "query": query,
                "num_results": len(results),
            },
        )
        return results

    def delete(self, doc_id: str) -> bool:
        """Delete a document by id using Rust or the SQLite fallback."""
        if self._rust_impl is not None:
            return self._rust_impl.delete(doc_id)
        assert self._conn is not None
        result = self._conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        self._conn.execute("DELETE FROM documents_fts_python WHERE doc_id = ?", (doc_id,))
        self._conn.commit()
        return result.rowcount == 1

    def clear(self) -> None:
        """Remove all stored documents."""
        if self._rust_impl is not None:
            self._rust_impl.clear()
            return
        assert self._conn is not None
        self._conn.execute("DELETE FROM documents")
        self._conn.execute("DELETE FROM documents_fts_python")
        self._conn.commit()

    def count(self) -> int:
        """Return the number of stored documents."""
        if self._rust_impl is not None:
            return self._rust_impl.count()
        assert self._conn is not None
        return int(self._conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0])

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None


__all__ = ["SQLiteMemory"]
