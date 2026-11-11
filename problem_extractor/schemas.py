"""문제 추출 결과의 데이터 구조.

Claude 구조화 출력(output_format)에 그대로 쓰이는 모델과,
API 응답/요청에 쓰이는 모델이 함께 들어 있다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ProblemType = Literal["multiple_choice", "short_answer", "essay", "true_false", "other"]
Confidence = Literal["high", "medium", "low"]
FigureKind = Literal["graph", "geometry", "table", "diagram", "picture", "other"]


# ---------------------------------------------------------------------------
# Claude가 채우는 모델 (구조화 출력 스키마)
# ---------------------------------------------------------------------------


class BBox(BaseModel):
    """이미지 기준 정규화 좌표(0~1). (x0, y0)이 왼쪽 위, (x1, y1)이 오른쪽 아래."""

    x0: float
    y0: float
    x1: float
    y1: float


class Choice(BaseModel):
    label: str = Field(description="보기 기호 그대로. 예: ①, ②, (가), A")
    text: str = Field(description="보기 내용. 수식은 $...$ LaTeX")


class PointLabel(BaseModel):
    label: str = Field(description="그림에 적힌 점 이름 그대로. 예: A, P, O")
    coordinates: str | None = Field(
        default=None, description="그림에 좌표가 인쇄돼 있을 때만 그대로. 예: '(2, 0)'. 없으면 null (추측 금지)"
    )


class Figure(BaseModel):
    kind: FigureKind = Field(
        default="other",
        description="graph: 좌표평면 위 그래프, geometry: 도형, table: 표, diagram: 수직선·벤다이어그램·순서도 등, "
        "picture: 삽화·사진, other: 그 밖",
    )
    description: str = Field(description="그림/그래프/도형/표를 한 문장으로 설명")
    bbox: BBox
    equations: list[str] = Field(
        default_factory=list,
        description="그림 안에 직접 적힌 식만 LaTeX로. 예: 그래프 옆의 'y=x^2-4'. 없으면 빈 배열 (발문의 식을 옮기지 말 것)",
    )
    points: list[PointLabel] = Field(default_factory=list, description="그림에 이름이 붙은 점들. 없으면 빈 배열")
    table_markdown: str | None = Field(
        default=None, description="kind가 table일 때 표 내용을 Markdown 표로. 칸 안의 수식은 $...$. 표가 아니면 null"
    )


class ExtractedProblem(BaseModel):
    number: str | None = Field(description="문제 번호 그대로. 예: '3', '예제 2', '유제 1-2'. 없으면 null")
    problem_type: ProblemType
    shared_context: str | None = Field(
        description="여러 문제가 공유하는 지문/조건(예: '[3~4] 다음 그림을 보고...'). 없으면 null"
    )
    stem: str = Field(description="발문. Markdown, 수식은 인라인 $...$ / 블록 $$...$$ LaTeX")
    choices: list[Choice] = Field(description="객관식 보기. 객관식이 아니면 빈 배열")
    answer: str | None = Field(description="페이지에 정답이 인쇄돼 있을 때만. 직접 풀지 말 것. 없으면 null")
    solution: str | None = Field(description="페이지에 해설이 인쇄돼 있을 때만. 없으면 null")
    topic: str | None = Field(description="페이지에 보이는 단원/소단원명. 없으면 null")
    tags: list[str] = Field(description="수학 개념 태그 1~4개. 예: '이차방정식', '근의 공식'")
    points: float | None = Field(description="배점이 인쇄돼 있으면 숫자, 없으면 null")
    bbox: BBox = Field(description="문제 전체(번호~보기 끝) 영역")
    figures: list[Figure] = Field(description="문제에 딸린 그림·그래프·도형·표. 없으면 빈 배열")
    confidence: Confidence = Field(description="전사 정확도에 대한 자신감. 흐리거나 잘린 부분이 있으면 low")
    notes: str | None = Field(description="검수자가 알아야 할 점(잘림, 판독 불가 등). 없으면 null")


class PageExtraction(BaseModel):
    page_title: str | None = Field(description="페이지 상단의 책/단원 제목. 없으면 null")
    problems: list[ExtractedProblem]


# ---------------------------------------------------------------------------
# API 입출력 모델
# ---------------------------------------------------------------------------


class FigureOut(BaseModel):
    id: int
    problem_id: int
    kind: FigureKind
    description: str
    bbox: BBox
    equations: list[str]
    points: list[PointLabel]
    table_markdown: str | None
    url: str = Field(description="잘라낸 그림 PNG. 영역을 바꾸면 ?v= 값이 바뀐다")


class FigurePatch(BaseModel):
    """그림 정보 수정. bbox를 보내면 원본 페이지에서 그 영역으로 다시 잘라낸다."""

    kind: FigureKind | None = None
    description: str | None = None
    bbox: BBox | None = None
    equations: list[str] | None = None
    points: list[PointLabel] | None = None
    table_markdown: str | None = None


class FigureCreate(BaseModel):
    """검수 중에 모델이 놓친 그림을 직접 추가."""

    bbox: BBox
    kind: FigureKind = "other"
    description: str = ""


class ProblemOut(BaseModel):
    id: int
    source_id: int
    number: str | None
    problem_type: ProblemType
    shared_context: str | None
    stem: str
    choices: list[Choice]
    answer: str | None
    solution: str | None
    topic: str | None
    tags: list[str]
    points: float | None
    confidence: Confidence
    notes: str | None
    reviewed: bool
    created_at: str
    updated_at: str
    bbox: BBox | None = None
    image_url: str = Field(description="원본 페이지에서 이 문제 영역만 잘라낸 PNG")
    figures: list[FigureOut]


class SourceOut(BaseModel):
    id: int
    filename: str | None
    sha256: str
    page_title: str | None
    model: str | None
    created_at: str
    problem_count: int
    image_url: str = Field(description="원본 페이지 PNG")


class ExtractResponse(BaseModel):
    source: SourceOut
    problems: list[ProblemOut]
    duplicate: bool = Field(description="같은 이미지를 이미 처리해서 저장된 결과를 돌려준 경우 true")


class ProblemPatch(BaseModel):
    """검수 화면에서 고친 값. 보낸 필드만 바뀐다."""

    number: str | None = None
    problem_type: ProblemType | None = None
    shared_context: str | None = None
    stem: str | None = None
    choices: list[Choice] | None = None
    answer: str | None = None
    solution: str | None = None
    topic: str | None = None
    tags: list[str] | None = None
    points: float | None = None
    notes: str | None = None
    reviewed: bool | None = None


class ProblemList(BaseModel):
    total: int
    items: list[ProblemOut]
