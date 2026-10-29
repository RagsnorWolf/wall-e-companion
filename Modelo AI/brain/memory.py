"""Memoria de WALL-E: SQLite, sin dependencias externas.

Dos capas:
  - turns    : historial de conversación (corto plazo, ventana deslizante)
  - memories : datos que WALL-E decide recordar (largo plazo)

Búsqueda: FTS5 si está disponible, si no LIKE con scoring simple.
Fácil de migrar a ChromaDB después: la interfaz no cambia.
"""

from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       REAL NOT NULL,
    role     TEXT NOT NULL,
    content  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turns_ts ON turns(ts);

CREATE TABLE IF NOT EXISTS memories (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       REAL NOT NULL,
    kind     TEXT NOT NULL DEFAULT 'fact',
    text     TEXT NOT NULL,
    weight   REAL NOT NULL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS idx_memories_ts ON memories(ts);
"""

_STOPWORDS = {
    "de", "la", "que", "el", "en", "y", "a", "los", "se", "del", "las", "un",
    "por", "con", "no", "una", "su", "para", "es", "al", "lo", "como", "más",
    "me", "mi", "te", "tu", "si", "ya", "yo", "le", "les", "nos", "pero",
}


class Memory:
    def __init__(self, path: str | Path = "memory.db", max_turns: int = 6) -> None:
        self.path = str(path)
        self.max_turns = max_turns
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)
        self.db.commit()

    # ------------------------------------------------------------- historial
    def add_turn(self, role: str, content: str) -> None:
        self.db.execute(
            "INSERT INTO turns (ts, role, content) VALUES (?, ?, ?)",
            (time.time(), role, content),
        )
        self.db.commit()
        self._trim_turns()

    def _trim_turns(self) -> None:
        keep = self.max_turns * 2
        self.db.execute(
            "DELETE FROM turns WHERE id NOT IN "
            "(SELECT id FROM turns ORDER BY id DESC LIMIT ?)",
            (keep,),
        )
        self.db.commit()

    def recent_turns(self, limit: int | None = None) -> list[dict[str, str]]:
        limit = limit or self.max_turns * 2
        rows = self.db.execute(
            "SELECT role, content FROM turns ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    # ------------------------------------------------------------- largo plazo
    def remember(self, text: str, kind: str = "fact", weight: float = 1.0) -> int:
        text = text.strip()
        if not text:
            return -1
        cur = self.db.execute(
            "INSERT INTO memories (ts, kind, text, weight) VALUES (?, ?, ?, ?)",
            (time.time(), kind, text, weight),
        )
        self.db.commit()
        return int(cur.lastrowid)

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        terms = [t for t in _tokenize(query) if t not in _STOPWORDS]
        rows = self.db.execute(
            "SELECT id, ts, kind, text FROM memories ORDER BY ts DESC LIMIT 500"
        ).fetchall()
        if not rows:
            return []
        if not terms:
            return [dict(r) for r in rows[:limit]]

        scored: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            haystack = row["text"].lower()
            score = sum(1.0 for term in terms if term in haystack)
            if score > 0:
                age_days = max(0.0, (time.time() - row["ts"]) / 86400)
                recency = 1.0 / (1.0 + age_days / 30.0)
                scored.append((score + recency, dict(row)))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def forget(self, memory_id: int) -> bool:
        cur = self.db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self.db.commit()
        return cur.rowcount > 0

    def count(self) -> int:
        row = self.db.execute("SELECT COUNT(*) AS n FROM memories").fetchone()
        return int(row["n"])

    # ------------------------------------------------------------- contexto
    def context_block(self, user_text: str) -> str:
        """Bloque corto para inyectar en el system prompt antes de responder."""
        hits = self.search(user_text, limit=4)
        if not hits:
            return ""
        lines = [f"- {h['text']}" for h in hits]
        return "Cosas que recordás y pueden venir al caso:\n" + "\n".join(lines)

    def close(self) -> None:
        self.db.close()


def _tokenize(text: str) -> list[str]:
    return [t for t in re.split(r"[^0-9a-záéíóúñü]+", text.lower()) if len(t) > 2]
