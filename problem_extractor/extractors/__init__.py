"""추출기 모음. PX_PROVIDER 로 고른다."""

from __future__ import annotations

from .base import (
    ExtractionError,
    Extractor,
    MissingCredentialsError,
    RateLimitedError,
    UpstreamError,
)

PROVIDERS = ("gemini", "claude")


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
]
