"""웹 화면을 index.html 한 파일로 묶는다 (Vercel·Netlify 등에 드래그해서 올리는 용도).

    python scripts/build_standalone.py          # dist/index.html 생성

한 파일 버전은 API 서버를 같은 주소에서 찾지 않고, 화면에서 정한 주소
(기본 http://localhost:8000)로 요청을 보낸다. 서버의 .env에 PX_CORS_ORIGINS로
올린 사이트 주소를 적어야 브라우저가 요청을 허용한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "problem_extractor" / "web"


def build() -> str:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    css = (WEB / "style.css").read_text(encoding="utf-8")
    js = (WEB / "app.js").read_text(encoding="utf-8")

    css_tag = '<link rel="stylesheet" href="/static/style.css">'
    js_tag = '<script defer src="/static/app.js"></script>'
    for tag in (css_tag, js_tag):
        if tag not in html:
            raise SystemExit(f"index.html에서 {tag} 를 찾지 못했어요.")
    if "</script" in js.lower():
        raise SystemExit("app.js 안에 </script 가 있으면 한 파일로 묶을 수 없어요.")

    html = html.replace(css_tag, f"<style>\n{css}</style>")
    html = html.replace(js_tag, "")
    # 인라인 스크립트는 defer가 안 먹으니 body 끝에 둔다. app.js가 DOMContentLoaded까지 기다린다.
    html = html.replace(
        "</body>",
        f"<script>window.PX_STANDALONE = true;</script>\n<script>\n{js}</script>\n</body>",
    )
    return html


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(), encoding="utf-8")
    print(f"만들었어요: {out}")


if __name__ == "__main__":
    main()
