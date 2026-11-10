"""모든 추출기가 공유하는 인터페이스, 프롬프트, 오류."""

from __future__ import annotations

from typing import Protocol

from ..schemas import PageExtraction

SYSTEM_PROMPT = """\
당신은 수학 교과서·문제집 페이지 사진에서 문제를 정확히 전사해 구조화하는 도구입니다.

전사 규칙
- 페이지에 보이는 문제를 위에서 아래, 왼쪽 단에서 오른쪽 단 순서로 빠짐없이 추출합니다. \
개념 설명, 목차, 광고, 쪽 번호처럼 문제가 아닌 부분은 건너뜁니다.
- 글자는 보이는 그대로 옮깁니다. 문장을 다듬거나 요약하지 않습니다.
- 모든 수식은 LaTeX로 씁니다. 인라인은 $...$, 따로 떨어진 식은 $$...$$. \
분수 \\frac, 루트 \\sqrt, 지수·첨자, 벡터 \\vec, 극한 \\lim, 적분 \\int, 집합 기호, 부등호를 정확히 구분합니다.
- 객관식 보기는 choices에 넣고 stem에는 넣지 않습니다. 보기 기호(①, ②...)는 label에 그대로 둡니다.
- 정답과 해설은 페이지에 인쇄돼 있을 때만 채웁니다. 직접 풀어서 채우지 않습니다.
- 그림·그래프·도형·표는 figures에 영역(bbox)과 짧은 설명으로 남깁니다. \
표가 단순하면 stem 안에 Markdown 표로도 옮깁니다.
- 페이지 가장자리에서 잘린 문제도 보이는 만큼 옮기고 confidence를 low로, notes에 잘렸다고 씁니다.
- 판독이 애매한 글자는 가장 그럴듯한 값으로 쓰고 notes에 무엇이 애매했는지 남깁니다.

좌표
- bbox는 이미지 전체를 0~1로 정규화한 값입니다. (x0, y0)이 왼쪽 위, (x1, y1)이 오른쪽 아래입니다.
- 문제 bbox는 번호부터 마지막 보기까지 감쌉니다. 그림 bbox는 그림만 꼭 맞게 감쌉니다.

페이지에 문제가 하나도 없으면 problems를 빈 배열로 돌려줍니다.\
"""

USER_INSTRUCTION = "이 페이지의 문제를 모두 추출해 주세요."


class ExtractionError(RuntimeError):
    """모델 호출은 됐지만 쓸 수 있는 결과를 받지 못한 경우 (422)."""


class MissingCredentialsError(RuntimeError):
    """API 키가 없거나 잘못된 경우 (503)."""


class RateLimitedError(RuntimeError):
    """요청 한도(무료 등급 하루 한도 포함)에 걸린 경우 (429)."""


class UpstreamError(RuntimeError):
    """모델 제공사 서버 오류나 연결 실패 (502)."""


class Extractor(Protocol):
    model_name: str

    def extract(self, image_bytes: bytes, media_type: str) -> PageExtraction: ...
