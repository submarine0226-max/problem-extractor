"""Gemini(Google AI Studio) 추출기. 무료 등급 있음. 키: GEMINI_API_KEY

무료 등급에서는 보낸 데이터를 Google이 서비스 개선에 쓸 수 있어요.
"""

from __future__ import annotations

import os

from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from ..schemas import PageExtraction
from .base import (
    SYSTEM_PROMPT,
    USER_INSTRUCTION,
    ExtractionError,
    MissingCredentialsError,
    RateLimitedError,
    UpstreamError,
)

# 무료 등급 하루 한도가 넉넉한 Flash-Lite가 기본. 정확도가 아쉬우면 PX_MODEL=gemini-3.8-flash
DEFAULT_MODEL = "gemini-3.5-flash-lite"


class GeminiExtractor:
    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None, client: genai.Client | None = None):
        self.model_name = model
        if client is None:
            key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            if not key:
                # SDK에 키 없이 Client를 만들게 하면 실패하면서 정리 오류 로그를 남겨서, 미리 확인한다.
                raise MissingCredentialsError("GEMINI_API_KEY가 설정되지 않았어요.")
            client = genai.Client(api_key=key)
        self.client = client

    def extract(self, image_bytes: bytes, media_type: str) -> PageExtraction:
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=media_type),
                    USER_INSTRUCTION,
                ],
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_json_schema=PageExtraction.model_json_schema(),
                    max_output_tokens=32768,
                ),
            )
        except errors.ClientError as exc:
            if exc.code == 429:
                raise RateLimitedError("Gemini 요청 한도에 걸렸어요(무료 등급은 분당·하루 한도가 있어요).") from exc
            if exc.code in (401, 403) or (exc.code == 400 and "API key" in str(exc)):
                raise MissingCredentialsError("Gemini API 키가 잘못됐어요.") from exc
            if exc.code == 404:
                raise UpstreamError(f"모델 '{self.model_name}'을 찾을 수 없어요. PX_MODEL을 확인해 주세요.") from exc
            raise UpstreamError(f"Gemini API 오류 ({exc.code}): {exc.message}") from exc
        except errors.APIError as exc:
            raise UpstreamError(f"Gemini API 오류 ({exc.code}): {exc.message}") from exc

        candidate = (response.candidates or [None])[0]
        finish = getattr(candidate, "finish_reason", None)
        finish_name = getattr(finish, "name", str(finish))
        if finish_name == "MAX_TOKENS":
            raise ExtractionError("문제가 너무 많아 응답이 잘렸어요. 페이지를 나눠서 찍어 주세요.")
        if finish_name in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "RECITATION"):
            raise ExtractionError(f"모델이 이 이미지 처리를 거절했어요 ({finish_name}).")
        text = response.text
        if not text:
            raise ExtractionError("모델이 빈 응답을 돌려줬어요.")
        try:
            return PageExtraction.model_validate_json(text)
        except ValidationError as exc:
            raise ExtractionError("모델 응답이 스키마와 맞지 않아요. 다시 시도해 주세요.") from exc
