"""What a TLScontact window shows, read from its screenshot (text + colours).

The program may not read TLS's web pages directly (Cloudflare refuses browsers a
program controls), so it looks at the picture of the person's Edge window:

  * the reCAPTCHA box turns into a green tick once the person has solved it,
  * "Track my application" lists the steps; the current one has an orange clock,
    done ones a green dot, later ones an empty circle.
"""
from __future__ import annotations

import io
import re

from PIL import Image

from .ocr import Line

ROBOT = re.compile(r"i.?m\s*not\s*a\s*robot", re.I)      # OCR sometimes drops spaces
TRACK_TITLE = re.compile(r"track\s*my\s*application", re.I)

# The steps TLS shows today (others are still read, these just help spot them).
KNOWN_STEPS = ("appointment confirmed", "application documentation confirmed",
               "application transferred to consulate", "in process",
               "passport returning from consulate", "passport returned")


def _image(png: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png)).convert("RGB")


def _count(img: Image.Image, box: tuple[int, int, int, int], test) -> int:
    left, top, right, bottom = (max(0, box[0]), max(0, box[1]),
                                min(img.width, box[2]), min(img.height, box[3]))
    if right <= left or bottom <= top:
        return 0
    return sum(1 for px in img.crop((left, top, right, bottom)).getdata() if test(*px))


def _green(r: int, g: int, b: int) -> bool:          # reCAPTCHA's tick
    return g > 120 and g - r > 60 and g - b > 30


def _orange(r: int, g: int, b: int) -> bool:         # the current step's clock
    return r > 200 and 60 < g < 170 and b < 90


def _teal(r: int, g: int, b: int) -> bool:           # a done step's dot
    return g > 140 and b > 110 and r < 100


def robot_box(lines: list[Line]) -> Line | None:
    return next((l for l in lines if ROBOT.search(l.text)), None)


def ticked(png: bytes, robot: Line) -> bool:
    """True once the box left of "I'm not a robot" shows the green tick."""
    h = robot.bottom - robot.top
    box = (robot.left - 4 * h, robot.top - h, robot.left - 2, robot.bottom + h)
    return _count(_image(png), box, _green) >= 12


def steps(png: bytes, lines: list[Line]) -> list[tuple[str, str]]:
    """[(step, "done" | "current" | "next")] from the open "Track my application" box."""
    title = next((l for l in lines if TRACK_TITLE.search(l.text)), None)
    if not title:
        return []
    img = _image(png)
    out = []
    for line in lines:
        if line.top <= title.bottom or abs(line.left - title.left) > 12:
            continue                         # step texts line up under the title
        h = line.bottom - line.top
        icon = (line.left - 5 * h, line.top - h // 2, line.left - h // 2, line.bottom + h // 2)
        if _count(img, icon, _orange) >= 6:
            out.append((line.text, "current"))
        elif _count(img, icon, _teal) >= 6:
            out.append((line.text, "done"))
        else:
            out.append((line.text, "next"))
    return out


def status_of(found: list[tuple[str, str]]) -> str:
    """The step the application is at: the orange one, else the last done one."""
    current = [s for s, state in found if state == "current"]
    if current:
        return current[0]
    done = [s for s, state in found if state == "done"]
    return done[-1] if done else ""


def describe(found: list[tuple[str, str]]) -> str:
    mark = {"done": "✔", "current": "▶", "next": "○"}
    return "\n".join(f"{mark[state]} {s}" for s, state in found)


def stack(pictures: list[bytes]) -> bytes:
    """Several screenshots one under the other (one PDF page per client)."""
    images = [_image(p) for p in pictures if p]
    if len(images) == 1:
        buf = io.BytesIO(); images[0].save(buf, "PNG"); return buf.getvalue()
    width = max(i.width for i in images)
    out = Image.new("RGB", (width, sum(i.height for i in images)), "white")
    y = 0
    for i in images:
        out.paste(i, (0, y)); y += i.height
    buf = io.BytesIO(); out.save(buf, "PNG"); return buf.getvalue()
