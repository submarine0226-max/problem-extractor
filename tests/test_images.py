from PIL import Image

from problem_extractor.images import crop_bbox, prepare_image
from problem_extractor.schemas import BBox


def test_crop_pads_and_clamps():
    img = Image.new("RGB", (1000, 2000))
    out = crop_bbox(img, BBox(x0=0.0, y0=0.9, x1=0.5, y1=1.0), pad=0.01)
    assert out is not None
    assert out.size == (510, 220)


def test_crop_handles_swapped_coords():
    img = Image.new("RGB", (100, 100))
    out = crop_bbox(img, BBox(x0=0.8, y0=0.8, x1=0.2, y1=0.2), pad=0)
    assert out is not None and out.size == (60, 60)


def test_crop_rejects_empty_box():
    img = Image.new("RGB", (100, 100))
    assert crop_bbox(img, BBox(x0=0.5, y0=0.5, x1=0.5, y1=0.5), pad=0) is None


def test_prepare_downscales_for_model_only():
    import io

    buf = io.BytesIO()
    Image.new("RGB", (3000, 1500), "white").save(buf, format="PNG")
    prepared = prepare_image(buf.getvalue(), max_side=1000)
    assert prepared.image.size == (3000, 1500)
    assert Image.open(io.BytesIO(prepared.model_bytes)).size == (1000, 500)


def test_trim_margins_removes_blank_border_only():
    from problem_extractor.images import trim_margins

    img = Image.new("RGB", (400, 300), (235, 232, 225))  # 사진 속 종이처럼 약간 누런 배경
    img.paste((20, 20, 20), (100, 100, 200, 150))
    out = trim_margins(img)
    pad = round(0.02 * 400)
    assert out.size == (100 + 2 * pad, 50 + 2 * pad)

    blank = Image.new("RGB", (200, 200), "white")
    assert trim_margins(blank).size == (200, 200)  # 내용이 없으면 그대로

    speck = Image.new("RGB", (200, 200), "white")
    speck.putpixel((5, 5), (0, 0, 0))
    assert trim_margins(speck).size == (200, 200)  # 얼룩 하나는 믿지 않는다
