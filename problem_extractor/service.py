"""업로드 → 전처리 → 추출 → 그림 크롭 → DB 저장 흐름."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from PIL import Image

from .config import Settings
from .db import Database
from .extractors import Extractor
from .images import crop_bbox, prepare_image, to_png_bytes
from .schemas import BBox, Choice, ExtractResponse, FigureOut, ProblemOut, SourceOut


class ProblemService:
    def __init__(self, settings: Settings, db: Database, extractor: Extractor | None) -> None:
        self.settings = settings
        self.db = db
        self.extractor = extractor
        for d in (settings.figures_dir, settings.sources_dir):
            d.mkdir(parents=True, exist_ok=True)

    # --- 추출 --------------------------------------------------------------

    def extract_and_store(self, data: bytes, filename: str | None, force: bool = False) -> ExtractResponse:
        sha = hashlib.sha256(data).hexdigest()
        existing = self.db.find_source_by_hash(sha)
        if existing is not None and not force:
            return self._response_for_source(existing["id"], duplicate=True)
        if existing is not None and force:
            self.delete_source(existing["id"])

        prepared = prepare_image(data, self.settings.max_image_side)
        page = self.extractor.extract(prepared.model_bytes, prepared.media_type)

        src_rel = f"sources/{sha}.png"
        (self.settings.data_dir / src_rel).write_bytes(to_png_bytes(prepared.image))

        problems = []
        for pi, problem in enumerate(page.problems):
            p = problem.model_dump()
            for fi, fig in enumerate(p["figures"]):
                crop = crop_bbox(prepared.image, problem.figures[fi].bbox)
                if crop is None:
                    fig["path"] = None
                    continue
                rel = f"figures/{sha[:16]}_{pi}_{fi}.png"
                (self.settings.data_dir / rel).write_bytes(to_png_bytes(crop))
                fig["path"] = rel
            problems.append(p)

        source_id = self.db.insert_extraction(
            filename=filename,
            sha256=sha,
            page_title=page.page_title,
            model=self.extractor.model_name,
            image_path=src_rel,
            raw_json=page.model_dump_json(),
            problems=problems,
        )
        return self._response_for_source(source_id, duplicate=False)

    # --- 조회/변환 ---------------------------------------------------------

    def source_out(self, row: sqlite3.Row) -> SourceOut:
        return SourceOut(
            id=row["id"],
            filename=row["filename"],
            sha256=row["sha256"],
            page_title=row["page_title"],
            model=row["model"],
            created_at=row["created_at"],
            problem_count=self.db.count_problems(row["id"]),
            image_url=f"/sources/{row['id']}/image",
        )

    def problems_out(self, rows: list[sqlite3.Row]) -> list[ProblemOut]:
        figs = self.db.get_figures([r["id"] for r in rows])
        return [
            ProblemOut(
                id=r["id"],
                source_id=r["source_id"],
                number=r["number"],
                problem_type=r["problem_type"],
                shared_context=r["shared_context"],
                stem=r["stem"],
                choices=[Choice(**c) for c in json.loads(r["choices_json"])],
                answer=r["answer"],
                solution=r["solution"],
                topic=r["topic"],
                tags=json.loads(r["tags_json"]),
                points=r["points"],
                confidence=r["confidence"],
                notes=r["notes"],
                reviewed=bool(r["reviewed"]),
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                bbox=BBox(**json.loads(r["bbox_json"])) if r["bbox_json"] else None,
                image_url=f"/problems/{r['id']}/image",
                figures=[
                    FigureOut(
                        id=f["id"],
                        description=f["description"],
                        bbox=BBox(**json.loads(f["bbox_json"])),
                        url=f"/figures/{f['id']}",
                    )
                    for f in figs.get(r["id"], [])
                ],
            )
            for r in rows
        ]

    def _response_for_source(self, source_id: int, duplicate: bool) -> ExtractResponse:
        src = self.db.get_source(source_id)
        assert src is not None
        _, rows = self.db.search_problems(source_id=source_id, limit=10_000)
        return ExtractResponse(source=self.source_out(src), problems=self.problems_out(rows), duplicate=duplicate)

    # --- 삭제 --------------------------------------------------------------

    def _unlink(self, rel_paths: list[str]) -> None:
        for rel in rel_paths:
            path = (self.settings.data_dir / rel).resolve()
            if self.settings.data_dir in path.parents:
                path.unlink(missing_ok=True)

    def delete_source(self, source_id: int) -> bool:
        if self.db.get_source(source_id) is None:
            return False
        self._unlink(self.db.delete_source(source_id))
        return True

    def delete_problem(self, problem_id: int) -> bool:
        paths = self.db.delete_problem(problem_id)
        if paths is None:
            return False
        self._unlink(paths)
        return True

    def _safe_path(self, rel: str | None) -> Path | None:
        if not rel:
            return None
        path = (self.settings.data_dir / rel).resolve()
        return path if path.is_file() and self.settings.data_dir in path.parents else None

    def figure_path(self, figure_id: int) -> Path | None:
        row = self.db.get_figure(figure_id)
        return None if row is None else self._safe_path(row["path"])

    def source_image_path(self, source_id: int) -> Path | None:
        row = self.db.get_source(source_id)
        return None if row is None else self._safe_path(row["image_path"])

    def problem_image_png(self, problem_id: int) -> bytes | None:
        """검수용: 원본 페이지에서 문제 영역을 넉넉하게 잘라낸다. bbox가 이상하면 페이지 전체."""
        row = self.db.get_problem(problem_id)
        if row is None:
            return None
        path = self.source_image_path(row["source_id"])
        if path is None:
            return None
        with Image.open(path) as img:
            img.load()
            crop = None
            if row["bbox_json"]:
                crop = crop_bbox(img, BBox(**json.loads(row["bbox_json"])), pad=0.03)
            return to_png_bytes(crop if crop is not None else img)
