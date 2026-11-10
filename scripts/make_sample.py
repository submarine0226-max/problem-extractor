"""직접 만든 샘플 문제 페이지 이미지를 그린다 (저작권 걱정 없는 테스트용).

    python scripts/make_sample.py            # samples/sample_page.png 생성
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "C:/Windows/Fonts/malgun.ttf",  # Windows
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",  # macOS
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",  # Ubuntu (fonts-nanum)
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


def load_font(size: int) -> ImageFont.ImageFont:
    for cand in FONT_CANDIDATES:
        if Path(cand).is_file():
            return ImageFont.truetype(cand, size)
    print("한글 폰트를 찾지 못해 기본 폰트를 씁니다(한글이 깨질 수 있어요).", file=sys.stderr)
    return ImageFont.load_default(size)


def draw_page() -> Image.Image:
    W, H = 1400, 1900
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    title, body, small = load_font(44), load_font(34), load_font(28)

    d.text((80, 60), "II. 이차방정식  |  2. 근의 공식", font=title, fill="black")
    d.line((80, 130, W - 80, 130), fill="black", width=3)

    y = 180
    d.text((80, y), "1. 이차방정식 x² - 5x + 6 = 0 의 두 근의 합은?", font=body, fill="black")
    y += 70
    for i, c in enumerate(["① 2", "② 3", "③ 5", "④ 6", "⑤ 11"]):
        d.text((120 + i * 230, y), c, font=body, fill="black")

    y += 140
    d.text((80, y), "2. 이차방정식 2x² + 3x - 2 = 0 을 근의 공식을 이용하여 푸시오.", font=body, fill="black")

    y += 200
    d.text((80, y), "3. 오른쪽 그림과 같이 이차함수 y = x² - 4 의 그래프가", font=body, fill="black")
    d.text((120, y + 50), "x축과 만나는 두 점을 A, B라 할 때, 선분 AB의 길이를 구하시오.", font=body, fill="black")
    # 그래프 그림
    gx, gy, gw, gh = 820, y + 140, 460, 420
    d.rectangle((gx, gy, gx + gw, gy + gh), outline="gray", width=2)
    ox, oy = gx + gw // 2, gy + 220  # 원점 (꼭짓점 (0,-4)가 gy+380에 오도록)
    d.line((gx + 20, oy, gx + gw - 20, oy), fill="black", width=2)
    d.line((ox, gy + 20, ox, gy + gh - 20), fill="black", width=2)
    s = 40  # 1 단위 픽셀
    pts = [(ox + x / 10 * s, oy - ((x / 10) ** 2 - 4) * s) for x in range(-28, 29)]
    pts = [(px, py) for px, py in pts if gy + 10 < py < gy + gh - 10]
    d.line(pts, fill="blue", width=3)
    d.text((ox - 2 * s - 18, oy + 8), "A", font=small, fill="black")
    d.text((ox + 2 * s + 4, oy + 8), "B", font=small, fill="black")
    d.text((ox + 6, oy + 4), "O", font=small, fill="black")

    y += 640
    d.text((80, y), "4. x에 대한 이차방정식 x² + 2kx + k + 6 = 0 이 중근을 가질 때,", font=body, fill="black")
    d.text((120, y + 50), "양수 k의 값은? [4점]", font=body, fill="black")
    for i, c in enumerate(["① 1", "② 2", "③ 3", "④ 4", "⑤ 5"]):
        d.text((120 + i * 230, y + 130), c, font=body, fill="black")

    d.text((W // 2 - 20, H - 80), "- 42 -", font=small, fill="gray")
    return img


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "samples/sample_page.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    draw_page().save(out)
    print(f"saved {out}")
