"""Claude(Anthropic API) 추출기. 유료. 키: ANTHROPIC_API_KEY"""

from __future__ import annotations

import base64

import anthropic

from ..schemas import PageExtraction
from .base import (
    SYSTEM_PROMPT,
    USER_INSTRUCTION,
    ExtractionError,
    MissingCredentialsError,
    RateLimitedError,
    UpstreamError,
)

DEFAULT_MODEL = "claude-opus-5-5"


class ClaudeExtractor:
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        effort: str = "medium",
        client: anthropic.Anthropic | None = None,
    ) -> None:
        self.model_name = model
        self.effort = effort
        self.client = client or anthropic.Anthropic()

    def extract(self, image_bytes: bytes, media_type: str) -> PageExtraction:
        image_b64 = base64.standard_b64encode(image_bytes).decode("ascii")
        try:
            response = self.client.beta.messages.parse(
                model=self.model_name,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                # 모델이 안전 분류기에 걸려 거절하면 서버가 다른 모델로 자동 재시도한다.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={"effort": self.effort},
                output_format=PageExtraction,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {"type": "base64", "media_type": media_type, "data": image_b64},
                            },
                            {"type": "text", "text": USER_INSTRUCTION},
                        ],
                    }
                ],
            )
        except TypeError as exc:
            # SDK는 인증 정보가 하나도 없을 때 요청 시점에 TypeError를 던진다.
            if "authentication" in str(exc):
                raise MissingCredentialsError("ANTHROPIC_API_KEY가 설정되지 않았어요.") from exc
            raise
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise MissingCredentialsError("Anthropic API 키가 잘못됐어요.") from exc
        except anthropic.RateLimitError as exc:
            raise RateLimitedError("Anthropic API 요청 한도에 걸렸어요.") from exc
        except anthropic.APIConnectionError as exc:
            raise UpstreamError("Anthropic API에 연결하지 못했어요.") from exc
        except anthropic.APIStatusError as exc:
            raise UpstreamError(f"Anthropic API 오류 ({exc.status_code}): {exc.message}") from exc

        if response.stop_reason == "refusal":
            raise ExtractionError("모델이 이 이미지 처리를 거절했어요.")
        if response.stop_reason == "max_tokens":
            raise ExtractionError("문제가 너무 많아 응답이 잘렸어요. 페이지를 나눠서 찍어 주세요.")
        if response.parsed_output is None:
            raise ExtractionError("모델 응답을 해석하지 못했어요.")
        return response.parsed_output
