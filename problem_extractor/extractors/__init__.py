"""추출기 모음. PX_PROVIDER 로 고른다."""

from __future__ import annotations

import os

from .base import (
    ExtractionError,
    Extractor,
    MissingCredentialsError,
    RateLimitedError,
    UpstreamError,
)

PROVIDERS = ("gemini", "claude")


# 제공사별 기본 모델. 실제 값은 각 모듈의 DEFAULT_MODEL (SDK를 import하지 않고 보여주려고 여기 둔다)
DEFAULT_MODELS = {"gemini": "gemini-3.5-flash-lite", "claude": "claude-opus-5-5"}
CREDENTIAL_ENV = {"gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"), "claude": ("ANTHROPIC_API_KEY",)}


def has_credentials(provider: str) -> bool | None:
    """키가 환경 변수에 있으면 True, 없으면 False. claude는 `ant auth login`도 되니 없으면 None(모름)."""
    found = any(os.environ.get(k) for k in CREDENTIAL_ENV.get(provider, ()))
    if found:
        return True
    return None if provider == "claude" else False


def build_extractor(provider: str, model: str | None = None, effort: str = "medium") -> Extractor:
    """SDK는 고른 제공사 것만 import 한다 (안 쓰는 SDK는 설치 안 해도 됨)."""
    if provider == "gemini":
        from .gemini import DEFAULT_MODEL, GeminiExtractor

        return GeminiExtractor(model=model or DEFAULT_MODEL)
    if provider == "claude":
        from .claude import DEFAULT_MODEL, ClaudeExtractor

        return ClaudeExtractor(model=model or DEFAULT_MODEL, effort=effort)
    raise ValueError(f"PX_PROVIDER는 {', '.join(PROVIDERS)} 중 하나여야 해요: {provider!r}")


__all__ = [
    "PROVIDERS",
    "ExtractionError",
    "Extractor",
    "MissingCredentialsError",
    "RateLimitedError",
    "UpstreamError",
    "build_extractor",
    "DEFAULT_MODELS",
    "has_credentials",
]
