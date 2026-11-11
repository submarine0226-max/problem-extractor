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
    path         TEXT NOT NULL,
    kind            TEXT NOT NULL DEFAULT 'other',
    equations_json  TEXT NOT NULL DEFAULT '[]',
    points_json     TEXT NOT NULL DEFAULT '[]',
    table_markdown  TEXT
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


# 예전 버전으로 만든 DB에 없는 열 (열 이름, 정의). 시작할 때 없으면 추가한다.
MIGRATIONS = {
    "figures": [
        ("kind", "TEXT NOT NULL DEFAULT 'other'"),
        ("equations_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("points_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("table_markdown", "TEXT"),
    ],
}

FIGURE_PATCHABLE = {
    "kind": "kind",
    "description": "description",
    "bbox": "bbox_json",
    "equations": "equations_json",
    "points": "points_json",
    "table_markdown": "table_markdown",
    "path": "path",
}
FIGURE_JSON = {"bbox", "equations", "points"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            for table, columns in MIGRATIONS.items():
                have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
                for name, ddl in columns:
                    if name not in have:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

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
                    self._insert_figure(conn, problem_id, fpos, fig)
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

    @staticmethod
    def _insert_figure(conn: sqlite3.Connection, problem_id: int, position: int, fig: dict[str, Any]) -> int:
        cur = conn.execute(
            "INSERT INTO figures (problem_id, position, description, bbox_json, path,"
            " kind, equations_json, points_json, table_markdown) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                problem_id,
                position,
                fig.get("description") or "",
                json.dumps(fig["bbox"]),
                fig["path"],
                fig.get("kind") or "other",
                json.dumps(fig.get("equations") or [], ensure_ascii=False),
                json.dumps(fig.get("points") or [], ensure_ascii=False),
                fig.get("table_markdown"),
            ),
        )
        return cur.lastrowid

    def add_figure(self, problem_id: int, fig: dict[str, Any]) -> int:
        with self.connect() as conn:
            pos = conn.execute(
                "SELECT COALESCE(MAX(position) + 1, 0) FROM figures WHERE problem_id = ?", (problem_id,)
            ).fetchone()[0]
            fid = self._insert_figure(conn, problem_id, pos, fig)
            conn.execute("UPDATE problems SET updated_at = ? WHERE id = ?", (now_iso(), problem_id))
            return fid

    def update_figure(self, figure_id: int, changes: dict[str, Any]) -> bool:
        sets, args = [], []
        for key, value in changes.items():
            sets.append(f"{FIGURE_PATCHABLE[key]} = ?")
            args.append(json.dumps(value, ensure_ascii=False) if key in FIGURE_JSON else value)
        if not sets:
            return self.get_figure(figure_id) is not None
        with self.connect() as conn:
            cur = conn.execute(f"UPDATE figures SET {', '.join(sets)} WHERE id = ?", [*args, figure_id])
            conn.execute(
                "UPDATE problems SET updated_at = ? WHERE id = (SELECT problem_id FROM figures WHERE id = ?)",
                (now_iso(), figure_id),
            )
            return cur.rowcount > 0

    def delete_figure(self, figure_id: int) -> str | None:
        """지운 그림의 파일 경로. 없으면 None."""
        with self.connect() as conn:
            row = conn.execute("SELECT path, problem_id FROM figures WHERE id = ?", (figure_id,)).fetchone()
            if row is None:
                return None
            conn.execute("DELETE FROM figures WHERE id = ?", (figure_id,))
            conn.execute("UPDATE problems SET updated_at = ? WHERE id = ?", (now_iso(), row["problem_id"]))
            return row["path"]

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
            # 그림 설명·그림 속 식·표 내용도 함께 찾는다 (예: 'x^2-4' 로 그래프가 있는 문제 찾기)
            where.append(
                "(stem LIKE ? OR shared_context LIKE ? OR choices_json LIKE ? OR EXISTS ("
                "SELECT 1 FROM figures f WHERE f.problem_id = problems.id AND"
                " (f.description LIKE ? OR f.equations_json LIKE ? OR f.table_markdown LIKE ?)))"
            )
            like = f"%{q}%"
            args += [like] * 6
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
