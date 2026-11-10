"""실제 API를 부르지 않고 각 추출기의 요청 구성·응답 해석·오류 변환을 검사한다."""

from types import SimpleNamespace

import pytest
from google.genai import errors

from problem_extractor.extractors import (
    ExtractionError,
    MissingCredentialsError,
    RateLimitedError,
    UpstreamError,
    build_extractor,
)
from problem_extractor.extractors.gemini import GeminiExtractor

PAGE_JSON = (
    '{"page_title": "II", "problems": [{"number": "1", "problem_type": "multiple_choice",'
    ' "shared_context": null, "stem": "$x^2$", "choices": [{"label": "①", "text": "2"}],'
    ' "answer": null, "solution": null, "topic": null, "tags": ["이차방정식"], "points": null,'
    ' "bbox": {"x0": 0, "y0": 0, "x1": 1, "y1": 0.2}, "figures": [], "confidence": "high", "notes": null}]}'
)


class FakeModels:
    def __init__(self, text=PAGE_JSON, finish="STOP", error=None):
        self.text, self.finish, self.error = text, finish, error
        self.kwargs = None

    def generate_content(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        cand = SimpleNamespace(finish_reason=SimpleNamespace(name=self.finish))
        return SimpleNamespace(text=self.text, candidates=[cand])


def gemini(**kw):
    models = FakeModels(**kw)
    return GeminiExtractor(model="gemini-test", client=SimpleNamespace(models=models)), models


def test_gemini_parses_and_sends_schema():
    ext, models = gemini()
    page = ext.extract(b"img", "image/jpeg")
    assert page.problems[0].choices[0].label == "①"
    cfg = models.kwargs["config"]
    assert models.kwargs["model"] == "gemini-test"
    assert cfg.response_mime_type == "application/json"
    assert "problems" in cfg.response_json_schema["properties"]
    assert models.kwargs["contents"][0].inline_data.mime_type == "image/jpeg"


@pytest.mark.parametrize(
    "kw, exc",
    [
        ({"finish": "MAX_TOKENS"}, ExtractionError),
        ({"finish": "SAFETY"}, ExtractionError),
        ({"text": ""}, ExtractionError),
        ({"text": '{"problems": "nope"}'}, ExtractionError),
        ({"error": errors.ClientError(429, {"error": {"message": "quota"}})}, RateLimitedError),
        ({"error": errors.ClientError(403, {"error": {"message": "denied"}})}, MissingCredentialsError),
        ({"error": errors.ClientError(404, {"error": {"message": "no model"}})}, UpstreamError),
        ({"error": errors.ServerError(503, {"error": {"message": "busy"}})}, UpstreamError),
    ],
)
def test_gemini_error_mapping(kw, exc):
    ext, _ = gemini(**kw)
    with pytest.raises(exc):
        ext.extract(b"img", "image/jpeg")


def test_build_extractor(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    assert build_extractor("gemini").model_name == "gemini-3.5-flash-lite"
    assert build_extractor("gemini", "gemini-3.8-flash").model_name == "gemini-3.8-flash"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert build_extractor("claude").model_name == "claude-opus-5-5"
    with pytest.raises(ValueError):
        build_extractor("openai")
