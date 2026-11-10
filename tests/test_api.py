"""Anthropic API를 부르지 않고, 가짜 extractor로 전체 흐름을 검사한다."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from problem_extractor.api import create_app
from problem_extractor.config import Settings
from problem_extractor.extractors import ExtractionError, RateLimitedError
from problem_extractor.schemas import BBox, Choice, ExtractedProblem, Figure, PageExtraction


def make_problem(**overrides) -> ExtractedProblem:
    base = dict(
        number="1",
        problem_type="multiple_choice",
        shared_context=None,
        stem="이차방정식 $x^2-5x+6=0$의 두 근의 합은?",
        choices=[Choice(label=f"{c}", text=t) for c, t in zip("①②③④⑤", ["2", "3", "5", "6", "11"])],
        answer=None,
        solution=None,
        topic="근의 공식",
        tags=["이차방정식", "근과 계수의 관계"],
        points=None,
        bbox=BBox(x0=0.05, y0=0.09, x1=0.95, y1=0.2),
        figures=[],
        confidence="high",
        notes=None,
    )
    base.update(overrides)
    return ExtractedProblem(**base)


class FakeExtractor:
    model_name = "fake-model"

    def __init__(self, page: PageExtraction | None = None, error: Exception | None = None) -> None:
        self.page = page or PageExtraction(
            page_title="II. 이차방정식",
            problems=[
                make_problem(),
                make_problem(
                    number="3",
                    problem_type="short_answer",
                    stem="이차함수 $y=x^2-4$의 그래프가 $x$축과 만나는 두 점 A, B에 대해 $\\overline{AB}$를 구하시오.",
                    choices=[],
                    tags=["이차함수", "그래프"],
                    figures=[
                        Figure(description="y=x^2-4 그래프", bbox=BBox(x0=0.58, y0=0.4, x1=0.92, y1=0.62)),
                        Figure(description="뒤집힌 좌표", bbox=BBox(x0=0.5, y0=0.5, x1=0.5, y1=0.5)),
                    ],
                ),
            ],
        )
        self.error = error
        self.calls: list[tuple[int, str]] = []

    def extract(self, image_bytes: bytes, media_type: str) -> PageExtraction:
        self.calls.append((len(image_bytes), media_type))
        Image.open(io.BytesIO(image_bytes)).verify()  # 모델에 유효한 이미지를 보냈는지
        if self.error:
            raise self.error
        return self.page


def png_bytes(size=(1400, 1900), color="white") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path.resolve(), provider="fake", model=None, effort="low", max_image_side=1000, max_upload_mb=1)


@pytest.fixture
def fake() -> FakeExtractor:
    return FakeExtractor()


@pytest.fixture
def client(settings: Settings, fake: FakeExtractor) -> TestClient:
    return TestClient(create_app(settings, fake))


def upload(client: TestClient, data: bytes, name="page.png", **params):
    return client.post("/extract", files={"file": (name, data, "image/png")}, params=params)


def test_extract_stores_problems_and_figures(client, fake, settings):
    res = upload(client, png_bytes())
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["duplicate"] is False
    assert body["source"]["page_title"] == "II. 이차방정식"
    assert body["source"]["problem_count"] == 2
    assert body["source"]["model"] == "fake-model"

    p1, p3 = body["problems"]
    assert p1["number"] == "1"
    assert [c["text"] for c in p1["choices"]] == ["2", "3", "5", "6", "11"]
    assert p1["reviewed"] is False
    # 면적 0인 bbox는 버리고 정상 그림 하나만 저장
    assert len(p3["figures"]) == 1
    fig = client.get(p3["figures"][0]["url"])
    assert fig.status_code == 200 and fig.headers["content-type"] == "image/png"
    w, h = Image.open(io.BytesIO(fig.content)).size
    assert 400 < w < 600 and 400 < h < 500  # 원본(1400x1900) 해상도로 잘렸는지

    # 모델에는 축소본 JPEG이 갔는지
    assert fake.calls[0][1] == "image/jpeg"


def test_same_image_is_not_extracted_twice(client, fake):
    data = png_bytes()
    first = upload(client, data).json()
    second = upload(client, data).json()
    assert second["duplicate"] is True
    assert second["source"]["id"] == first["source"]["id"]
    assert len(fake.calls) == 1

    forced = upload(client, data, force="true").json()
    assert forced["duplicate"] is False
    assert len(fake.calls) == 2
    assert client.get("/sources").json()["total"] == 1


def test_search_filters(client):
    upload(client, png_bytes())
    assert client.get("/problems").json()["total"] == 2
    assert client.get("/problems", params={"tag": "이차함수"}).json()["total"] == 1
    assert client.get("/problems", params={"q": "x^2-5x"}).json()["total"] == 1
    assert client.get("/problems", params={"problem_type": "short_answer"}).json()["total"] == 1
    assert client.get("/problems", params={"topic": "근의"}).json()["total"] == 2
    assert client.get("/problems", params={"reviewed": "true"}).json()["total"] == 0


def test_patch_and_delete(client, settings):
    body = upload(client, png_bytes()).json()
    pid = body["problems"][0]["id"]

    res = client.patch(f"/problems/{pid}", json={"answer": "5", "reviewed": True, "tags": ["근과 계수의 관계"]})
    assert res.status_code == 200
    assert res.json()["answer"] == "5"
    assert res.json()["reviewed"] is True
    assert res.json()["tags"] == ["근과 계수의 관계"]
    assert client.patch(f"/problems/{pid}", json={"stem": None}).status_code == 422
    assert client.patch("/problems/9999", json={"answer": "1"}).status_code == 404

    fig_pid = body["problems"][1]["id"]
    assert len(list((settings.data_dir / "figures").iterdir())) == 1
    assert client.delete(f"/problems/{fig_pid}").status_code == 204
    assert client.get(f"/problems/{fig_pid}").status_code == 404
    assert list((settings.data_dir / "figures").iterdir()) == []

    sid = body["source"]["id"]
    assert client.delete(f"/sources/{sid}").status_code == 204
    assert client.get("/problems").json()["total"] == 0
    assert list((settings.data_dir / "sources").iterdir()) == []


def test_rejects_bad_uploads(client):
    assert upload(client, b"not an image").status_code == 415
    assert upload(client, b"").status_code == 400
    too_big = png_bytes() + b"\0" * (1024 * 1024)  # 설정 한도 1MB 초과
    assert upload(client, too_big).status_code == 413


def test_extraction_error_returns_422(settings):
    client = TestClient(create_app(settings, FakeExtractor(error=ExtractionError("거절"))))
    res = upload(client, png_bytes())
    assert res.status_code == 422
    assert client.get("/sources").json()["total"] == 0


def test_exif_rotation_and_rgba(client, fake):
    img = Image.new("RGBA", (300, 600), (255, 0, 0, 128))
    exif = img.getexif()
    exif[0x0112] = 6  # 90도 회전
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", exif=exif)
    assert upload(client, buf.getvalue(), name="rot.jpg").status_code == 200

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    assert upload(client, buf.getvalue(), name="rgba.png").status_code == 200


def test_rate_limit_returns_429(settings):
    client = TestClient(create_app(settings, FakeExtractor(error=RateLimitedError("한도"))))
    assert upload(client, png_bytes()).status_code == 429


def test_missing_gemini_key_returns_503(settings, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    from dataclasses import replace

    client = TestClient(create_app(replace(settings, provider="gemini")))
    res = upload(client, png_bytes())
    assert res.status_code == 503
    assert "GEMINI_API_KEY" in res.json()["detail"]
    assert client.get("/problems").status_code == 200  # 키 없어도 조회는 됨


def test_review_images_and_web_ui(client):
    body = upload(client, png_bytes()).json()
    p1 = body["problems"][0]
    assert p1["bbox"] == {"x0": 0.05, "y0": 0.09, "x1": 0.95, "y1": 0.2}

    crop = client.get(p1["image_url"])
    assert crop.status_code == 200 and crop.headers["content-type"] == "image/png"
    w, h = Image.open(io.BytesIO(crop.content)).size
    assert w < 1400 and h < 400  # 페이지 전체가 아니라 문제 영역만

    page = client.get(body["source"]["image_url"])
    assert page.status_code == 200
    assert Image.open(io.BytesIO(page.content)).size == (1400, 1900)

    assert client.get("/problems/9999/image").status_code == 404
    assert client.get("/sources/9999/image").status_code == 404

    index = client.get("/")
    assert index.status_code == 200 and "문제 추출기" in index.text
    assert client.get("/static/app.js").status_code == 200


def test_cors_only_for_allowed_origins(settings):
    from dataclasses import replace

    site = "https://my-problems.vercel.app"
    client = TestClient(create_app(replace(settings, cors_origins=(site,)), FakeExtractor()))
    preflight = {
        "Access-Control-Request-Method": "PATCH",
        "Access-Control-Request-Private-Network": "true",
    }
    ok = client.options("/problems/1", headers={"Origin": site, **preflight})
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == site
    assert ok.headers["access-control-allow-private-network"] == "true"

    bad = client.options("/problems/1", headers={"Origin": "https://evil.example", **preflight})
    assert bad.status_code == 400  # 출처 허용 헤더가 없으니 브라우저가 막는다
    assert "access-control-allow-origin" not in bad.headers

    # 설정하지 않으면 CORS 헤더 자체가 없다
    plain = TestClient(create_app(settings, FakeExtractor()))
    assert "access-control-allow-origin" not in plain.get("/health", headers={"Origin": site}).headers


def test_standalone_build_inlines_assets():
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts" / "build_standalone.py"
    spec = importlib.util.spec_from_file_location("build_standalone", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    html = mod.build()
    assert "/static/" not in html
    assert "window.PX_STANDALONE = true" in html
    assert html.index("PX_STANDALONE = true") < html.index("function start()") < html.index("</body>")
