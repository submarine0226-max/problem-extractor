"""이미지 전처리와 그림 영역 잘라내기."""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from .schemas import BBox

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


class InvalidImageError(ValueError):
    pass


@dataclass
class PreparedImage:
    image: Image.Image  # 회전 보정까지 끝난 원본 해상도 이미지 (그림 크롭용)
    model_bytes: bytes  # 모델에 보낼 축소본 (JPEG)
    media_type: str = "image/jpeg"


def prepare_image(data: bytes, max_side: int) -> PreparedImage:
    """EXIF 회전을 바로잡고 RGB로 맞춘 뒤, 모델용으로 긴 변을 max_side 이하로 줄인다.

    좌표는 0~1 정규화 값으로 주고받으므로, 축소본으로 받은 bbox를 원본에 그대로 쓸 수 있다.
    """
    try:
        img = Image.open(io.BytesIO(data))
        fmt = img.format
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidImageError("이미지 파일을 읽을 수 없어요.") from exc
    if fmt not in ALLOWED_FORMATS:
        raise InvalidImageError(f"지원하지 않는 형식이에요: {fmt}. JPEG, PNG, WEBP만 받아요.")

    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        background = Image.new("RGB", img.size, "white")
        rgba = img.convert("RGBA")
        background.paste(rgba, mask=rgba.split()[-1])
        img = background

    small = img.copy()
    small.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    small.save(buf, format="JPEG", quality=90)
    return PreparedImage(image=img, model_bytes=buf.getvalue())


def crop_bbox(img: Image.Image, bbox: BBox, pad: float = 0.015) -> Image.Image | None:
    """정규화 bbox로 잘라낸다. 모델 좌표는 대략적이라 약간 여유(pad)를 준다.

    좌표가 말이 안 되면(뒤집힘, 면적 0) None.
    """
    x0, x1 = sorted((bbox.x0, bbox.x1))
    y0, y1 = sorted((bbox.y0, bbox.y1))
    if x1 - x0 < 0.005 or y1 - y0 < 0.005:  # 모델이 의미 없는 좌표를 준 경우
        return None
    x0, y0 = max(0.0, x0 - pad), max(0.0, y0 - pad)
    x1, y1 = min(1.0, x1 + pad), min(1.0, y1 + pad)
    w, h = img.size
    box = (round(x0 * w), round(y0 * h), round(x1 * w), round(y1 * h))
    if box[2] - box[0] < 4 or box[3] - box[1] < 4:
        return None
    return img.crop(box)


def to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
