"""분석 결과를 sqlite에 캐시해서 동일한 (작성자, 기간) 조합에 대한 중복 API 호출을 막는다."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "cache.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author TEXT NOT NULL,
    period_key TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('summary', 'blog')),
    content TEXT NOT NULL,
    commit_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(author, period_key, kind)
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(SCHEMA)
        conn.commit()


def make_period_key(period_names: list[str]) -> str:
    return ",".join(sorted(period_names))


def get_cached(author: str, period_key: str, kind: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT content, commit_count, created_at FROM analysis_cache "
            "WHERE author = ? AND period_key = ? AND kind = ?",
            (author, period_key, kind),
        ).fetchone()
    if row is None:
        return None
    return {"content": row["content"], "commit_count": row["commit_count"], "created_at": row["created_at"]}


def save_cache(author: str, period_key: str, kind: str, content: str, commit_count: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO analysis_cache (author, period_key, kind, content, commit_count, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (author, period_key, kind, content, commit_count, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
