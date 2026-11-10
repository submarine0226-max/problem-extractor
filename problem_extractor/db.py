"""SQLite 저장소. 표준 라이브러리 sqlite3만 쓴다."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id          INTEGER PRIMARY KEY,
    filename    TEXT,
    sha256      TEXT NOT NULL UNIQUE,
    page_title  TEXT,
    model       TEXT,
    image_path  TEXT NOT NULL,
    raw_json    TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS problems (
    id              INTEGER PRIMARY KEY,
    source_id       INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    position        INTEGER NOT NULL,
    number          TEXT,
    problem_type    TEXT NOT NULL,
    shared_context  TEXT,
    stem            TEXT NOT NULL,
    choices_json    TEXT NOT NULL,
    answer          TEXT,
    solution        TEXT,
    topic           TEXT,
    tags_json       TEXT NOT NULL,
    points          REAL,
    confidence      TEXT NOT NULL,
    notes           TEXT,
    bbox_json       TEXT NOT NULL,
    reviewed        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_problems_source ON problems(source_id, position);

CREATE TABLE IF NOT EXISTS figures (
    id           INTEGER PRIMARY KEY,
    problem_id   INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
    position     INTEGER NOT NULL,
    description  TEXT NOT NULL,
    bbox_json    TEXT NOT NULL,
    path         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_figures_problem ON figures(problem_id, position);
"""

PATCHABLE_COLUMNS = {
    "number": "number",
    "problem_type": "problem_type",
    "shared_context": "shared_context",
    "stem": "stem",
    "choices": "choices_json",
    "answer": "answer",
    "solution": "solution",
    "topic": "topic",
    "tags": "tags_json",
    "points": "points",
    "notes": "notes",
    "reviewed": "reviewed",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # --- sources -----------------------------------------------------------

    def find_source_by_hash(self, sha256: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM sources WHERE sha256 = ?", (sha256,)).fetchone()

    def get_source(self, source_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()

    def count_problems(self, source_id: int) -> int:
        with self.connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM problems WHERE source_id = ?", (source_id,)
            ).fetchone()[0]

    def list_sources(self, limit: int, offset: int) -> tuple[int, list[sqlite3.Row]]:
        with self.connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM sources ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()
            return total, rows

    def delete_source(self, source_id: int) -> list[str]:
        """출처와 그 문제들을 지우고, 디스크에서 지워야 할 파일 경로를 돌려준다."""
        with self.connect() as conn:
            src = conn.execute("SELECT image_path FROM sources WHERE id = ?", (source_id,)).fetchone()
            if src is None:
                return []
            paths = [
                r["path"]
                for r in conn.execute(
                    "SELECT f.path FROM figures f JOIN problems p ON p.id = f.problem_id WHERE p.source_id = ?",
                    (source_id,),
                )
            ]
            conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
            return [*paths, src["image_path"]]

    # --- 저장 --------------------------------------------------------------

    def insert_extraction(
        self,
        *,
        filename: str | None,
        sha256: str,
        page_title: str | None,
        model: str,
        image_path: str,
        raw_json: str,
        problems: list[dict[str, Any]],
    ) -> int:
        """한 페이지 결과를 트랜잭션 하나로 저장한다.

        problems 각 항목: ExtractedProblem.model_dump() 에 figures[*]["path"] 가 채워진 dict.
        """
        ts = now_iso()
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO sources (filename, sha256, page_title, model, image_path, raw_json, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (filename, sha256, page_title, model, image_path, raw_json, ts),
            )
            source_id = cur.lastrowid
            for pos, p in enumerate(problems):
                cur = conn.execute(
                    "INSERT INTO problems (source_id, position, number, problem_type, shared_context, stem,"
                    " choices_json, answer, solution, topic, tags_json, points, confidence, notes, bbox_json,"
                    " reviewed, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
                    (
                        source_id,
                        pos,
                        p["number"],
                        p["problem_type"],
                        p["shared_context"],
                        p["stem"],
                        json.dumps(p["choices"], ensure_ascii=False),
                        p["answer"],
                        p["solution"],
                        p["topic"],
                        json.dumps(p["tags"], ensure_ascii=False),
                        p["points"],
                        p["confidence"],
                        p["notes"],
                        json.dumps(p["bbox"]),
                        ts,
                        ts,
                    ),
                )
                problem_id = cur.lastrowid
                for fpos, fig in enumerate(p["figures"]):
                    if not fig.get("path"):
                        continue
                    conn.execute(
                        "INSERT INTO figures (problem_id, position, description, bbox_json, path)"
                        " VALUES (?, ?, ?, ?, ?)",
                        (problem_id, fpos, fig["description"], json.dumps(fig["bbox"]), fig["path"]),
                    )
            return source_id

    # --- problems ----------------------------------------------------------

    def get_problem(self, problem_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM problems WHERE id = ?", (problem_id,)).fetchone()

    def get_figures(self, problem_ids: list[int]) -> dict[int, list[sqlite3.Row]]:
        if not problem_ids:
            return {}
        marks = ",".join("?" * len(problem_ids))
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM figures WHERE problem_id IN ({marks}) ORDER BY problem_id, position",
                problem_ids,
            ).fetchall()
        out: dict[int, list[sqlite3.Row]] = {}
        for r in rows:
            out.setdefault(r["problem_id"], []).append(r)
        return out

    def get_figure(self, figure_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM figures WHERE id = ?", (figure_id,)).fetchone()

    def search_problems(
        self,
        *,
        source_id: int | None = None,
        q: str | None = None,
        tag: str | None = None,
        topic: str | None = None,
        problem_type: str | None = None,
        reviewed: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, list[sqlite3.Row]]:
        where: list[str] = []
        args: list[Any] = []
        if source_id is not None:
            where.append("source_id = ?")
            args.append(source_id)
        if q:
            where.append("(stem LIKE ? OR shared_context LIKE ? OR choices_json LIKE ?)")
            like = f"%{q}%"
            args += [like, like, like]
        if tag:
            where.append("EXISTS (SELECT 1 FROM json_each(problems.tags_json) WHERE value = ?)")
            args.append(tag)
        if topic:
            where.append("topic LIKE ?")
            args.append(f"%{topic}%")
        if problem_type:
            where.append("problem_type = ?")
            args.append(problem_type)
        if reviewed is not None:
            where.append("reviewed = ?")
            args.append(int(reviewed))
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        with self.connect() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM problems {clause}", args).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM problems {clause} ORDER BY source_id, position LIMIT ? OFFSET ?",
                [*args, limit, offset],
            ).fetchall()
        return total, rows

    def update_problem(self, problem_id: int, changes: dict[str, Any]) -> bool:
        sets: list[str] = []
        args: list[Any] = []
        for key, value in changes.items():
            col = PATCHABLE_COLUMNS[key]
            if key in ("choices", "tags"):
                value = json.dumps(value, ensure_ascii=False)
            elif key == "reviewed":
                value = int(value)
            sets.append(f"{col} = ?")
            args.append(value)
        sets.append("updated_at = ?")
        args.append(now_iso())
        with self.connect() as conn:
            cur = conn.execute(f"UPDATE problems SET {', '.join(sets)} WHERE id = ?", [*args, problem_id])
            return cur.rowcount > 0

    def delete_problem(self, problem_id: int) -> list[str] | None:
        """지운 문제의 그림 파일 경로들. 문제가 없으면 None."""
        with self.connect() as conn:
            paths = [
                r["path"] for r in conn.execute("SELECT path FROM figures WHERE problem_id = ?", (problem_id,))
            ]
            cur = conn.execute("DELETE FROM problems WHERE id = ?", (problem_id,))
            return paths if cur.rowcount else None
