"""Put every client's screenshot into one PDF, one page per client:
the screenshot, with the client's full name typed under it."""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PAGE_WIDTH = 1240           # px; screenshots are scaled to this width
FOOTER = 90                 # height of the full-name strip under the screenshot


def _font(size: int):
    for name in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _page(png: bytes, full_name: str) -> Image.Image:
    shot = Image.open(io.BytesIO(png)).convert("RGB")
    if shot.width != PAGE_WIDTH:
        h = round(shot.height * PAGE_WIDTH / shot.width)
        shot = shot.resize((PAGE_WIDTH, h), Image.LANCZOS)
    page = Image.new("RGB", (PAGE_WIDTH, shot.height + FOOTER), "white")
    page.paste(shot, (0, 0))
    draw = ImageDraw.Draw(page)
    top = shot.height
    draw.line([0, top + 2, PAGE_WIDTH, top + 2], fill="#3D85C6", width=4)
    draw.text((24, top + 22), f"Full name:  {full_name or '— (no name in the sheet)'}",
              fill="#1A1A1A", font=_font(32))
    return page


def make_pdf(items: list[tuple[str, bytes]], path: Path) -> Path | None:
    """items: (full name, png bytes). Returns the PDF path, or None if empty."""
    pages = [_page(png, name) for name, png in items if png]
    if not pages:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(path, "PDF", resolution=150, save_all=True, append_images=pages[1:])
    return path
