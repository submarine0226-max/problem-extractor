"""FastAPI 앱. 실행: uvicorn problem_extractor.main:app --reload"""


import logging
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import __version__
from .config import Settings, load_settings
from .db import Database
from .extractors import (
    ExtractionError,
    Extractor,
    MissingCredentialsError,
    RateLimitedError,
    UpstreamError,
    build_extractor,
)
from .images import InvalidImageError
from .schemas import ExtractResponse, ProblemList, ProblemOut, ProblemPatch, ProblemType, SourceOut
from .service import ProblemService

log = logging.getLogger("problem_extractor")
WEB_DIR = Path(__file__).parent / "web"


def create_app(settings: Settings | None = None, extractor: Extractor | None = None) -> FastAPI:
    """테스트에서는 가짜 extractor를 넣어 API 호출 없이 돌린다."""
    settings = settings or load_settings()
    app = FastAPI(
        title="Problem Extractor",
        version=__version__,
        description="수학 교과서·문제집 사진에서 문제를 추출해 DB에 저장하는 API",
    )
    if settings.cors_origins:
        # Vercel 등 다른 주소에 올린 화면이 내 컴퓨터의 이 서버를 부를 수 있게 허용.
        # 허용 목록에 적은 사이트만 된다. (인증이 없어서 아무 사이트나 열면 DB를 지울 수 있게 됨)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Content-Type"],
            allow_private_network=True,  # https 사이트가 localhost를 부를 때 Chrome이 확인하는 부분
        )
    db = Database(settings.db_path)
    state: dict[str, ProblemService] = {}

    def get_service() -> ProblemService:
        if "svc" not in state:
            state["svc"] = ProblemService(settings, db, extractor)
        return state["svc"]

    def get_extractor() -> Extractor:
        # 모델 클라이언트는 첫 추출 요청 때 만든다. 키 없이도 조회 API는 쓸 수 있게.
        svc = get_service()
        if svc.extractor is None:
            try:
                svc.extractor = build_extractor(settings.provider, settings.model, settings.effort)
            except MissingCredentialsError as exc:
                raise HTTPException(503, f"{exc} .env를 확인해 주세요.") from exc
        return svc.extractor

    Svc = Annotated[ProblemService, Depends(get_service)]

    @app.get("/health")
    def health() -> dict[str, str | None]:
        return {"status": "ok", "version": __version__, "provider": settings.provider, "model": settings.model}

    @app.post("/extract", response_model=ExtractResponse, summary="사진 한 장에서 문제 추출 후 저장")
    async def extract(
        svc: Svc,
        file: Annotated[UploadFile, File(description="JPEG / PNG / WEBP 페이지 사진")],
        force: Annotated[bool, Query(description="같은 이미지를 이미 처리했어도 다시 추출")] = False,
    ) -> ExtractResponse:
        limit = settings.max_upload_mb * 1024 * 1024
        data = await file.read(limit + 1)
        if len(data) > limit:
            raise HTTPException(413, f"파일이 너무 커요. 최대 {settings.max_upload_mb}MB까지 받아요.")
        if not data:
            raise HTTPException(400, "빈 파일이에요.")
        get_extractor()
        try:
            # 모델 호출은 블로킹이라 스레드풀에서 돌린다.
            return await run_in_threadpool(svc.extract_and_store, data, file.filename, force)
        except InvalidImageError as exc:
            raise HTTPException(415, str(exc)) from exc
        except ExtractionError as exc:
            raise HTTPException(422, str(exc)) from exc
        except MissingCredentialsError as exc:
            raise HTTPException(503, f"{exc} .env를 확인해 주세요.") from exc
        except RateLimitedError as exc:
            raise HTTPException(429, f"{exc} 잠시 후 다시 시도해 주세요.") from exc
        except UpstreamError as exc:
            log.warning("upstream error: %s", exc)
            raise HTTPException(502, str(exc)) from exc

    @app.get("/problems", response_model=ProblemList, summary="문제 검색")
    def list_problems(
        svc: Svc,
        q: Annotated[str | None, Query(description="발문·보기 텍스트 검색")] = None,
        tag: str | None = None,
        topic: str | None = None,
        problem_type: ProblemType | None = None,
        source_id: int | None = None,
        reviewed: bool | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> ProblemList:
        total, rows = svc.db.search_problems(
            source_id=source_id,
            q=q,
            tag=tag,
            topic=topic,
            problem_type=problem_type,
            reviewed=reviewed,
            limit=limit,
            offset=offset,
        )
        return ProblemList(total=total, items=svc.problems_out(rows))

    @app.get("/problems/{problem_id}", response_model=ProblemOut)
    def get_problem(svc: Svc, problem_id: int) -> ProblemOut:
        row = svc.db.get_problem(problem_id)
        if row is None:
            raise HTTPException(404, "문제를 찾을 수 없어요.")
        return svc.problems_out([row])[0]

    @app.patch("/problems/{problem_id}", response_model=ProblemOut, summary="검수 후 수정")
    def patch_problem(svc: Svc, problem_id: int, patch: ProblemPatch) -> ProblemOut:
        changes = patch.model_dump(exclude_unset=True, mode="json")
        if changes.get("problem_type") is None:
            changes.pop("problem_type", None)
        for key in ("stem", "choices", "tags", "reviewed"):
            if key in changes and changes[key] is None:
                raise HTTPException(422, f"{key}는 null로 바꿀 수 없어요.")
        if changes and not svc.db.update_problem(problem_id, changes):
            raise HTTPException(404, "문제를 찾을 수 없어요.")
        return get_problem(svc, problem_id)

    @app.delete("/problems/{problem_id}", status_code=204)
    def delete_problem(svc: Svc, problem_id: int) -> Response:
        if not svc.delete_problem(problem_id):
            raise HTTPException(404, "문제를 찾을 수 없어요.")
        return Response(status_code=204)

    @app.get("/sources", summary="처리한 페이지 목록")
    def list_sources(
        svc: Svc,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict:
        total, rows = svc.db.list_sources(limit, offset)
        return {"total": total, "items": [svc.source_out(r) for r in rows]}

    @app.get("/sources/{source_id}", response_model=ExtractResponse)
    def get_source(svc: Svc, source_id: int) -> ExtractResponse:
        if svc.db.get_source(source_id) is None:
            raise HTTPException(404, "페이지를 찾을 수 없어요.")
        return svc._response_for_source(source_id, duplicate=False)

    @app.delete("/sources/{source_id}", status_code=204, summary="페이지와 그 문제들 삭제")
    def delete_source(svc: Svc, source_id: int) -> Response:
        if not svc.delete_source(source_id):
            raise HTTPException(404, "페이지를 찾을 수 없어요.")
        return Response(status_code=204)

    @app.get("/figures/{figure_id}", response_class=FileResponse, summary="잘라낸 그림 PNG")
    def get_figure(svc: Svc, figure_id: int) -> FileResponse:
        path = svc.figure_path(figure_id)
        if path is None:
            raise HTTPException(404, "그림을 찾을 수 없어요.")
        return FileResponse(path, media_type="image/png")

    @app.get("/sources/{source_id}/image", response_class=FileResponse, summary="원본 페이지 PNG")
    def get_source_image(svc: Svc, source_id: int) -> FileResponse:
        path = svc.source_image_path(source_id)
        if path is None:
            raise HTTPException(404, "페이지 이미지를 찾을 수 없어요.")
        return FileResponse(path, media_type="image/png")

    @app.get("/problems/{problem_id}/image", summary="원본에서 문제 영역만 잘라낸 PNG (검수용)")
    def get_problem_image(svc: Svc, problem_id: int) -> Response:
        png = svc.problem_image_png(problem_id)
        if png is None:
            raise HTTPException(404, "문제 이미지를 찾을 수 없어요.")
        return Response(png, media_type="image/png")

    # --- 웹 화면 (내 컴퓨터에서 쓰는 검수용 UI) ---------------------------------
    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    return app

