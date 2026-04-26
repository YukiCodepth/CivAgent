#!/usr/bin/env python3
"""Generate CivAgent raster icons from the vector brand direction."""

from __future__ import annotations

import math
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "assets" / "brand"
BUILD = ROOT / "build"
ICONSET = BUILD / "icon.iconset"


def ensure_dirs() -> None:
    BRAND.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    if ICONSET.exists():
        shutil.rmtree(ICONSET)
    ICONSET.mkdir(parents=True, exist_ok=True)


def rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size, size), radius=radius, fill=255)
    return mask


def draw_orbital_icon(size: int) -> Image.Image:
    scale = size / 1024
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    bg = Image.new("RGBA", (size, size), (5, 7, 6, 255))
    bg_draw = ImageDraw.Draw(bg)
    bg_draw.rounded_rectangle((0, 0, size, size), radius=int(216 * scale), fill=(5, 7, 6, 255))
    bg_draw.ellipse((int(-150 * scale), int(-170 * scale), int(810 * scale), int(790 * scale)), fill=(11, 29, 25, 255))
    bg_draw.ellipse((int(390 * scale), int(260 * scale), int(1180 * scale), int(1100 * scale)), fill=(27, 16, 10, 210))
    bg = bg.filter(ImageFilter.GaussianBlur(max(1, int(4 * scale))))
    image.alpha_composite(bg)

    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    bbox = tuple(int(v * scale) for v in (148, 148, 876, 876))
    for width, alpha in [(104, 44), (68, 78), (42, 128)]:
      glow_draw.arc(bbox, start=122, end=326, fill=(82, 224, 196, alpha), width=max(1, int(width * scale)))
      glow_draw.arc(bbox, start=320, end=58, fill=(255, 180, 84, alpha), width=max(1, int(width * scale)))
    glow = glow.filter(ImageFilter.GaussianBlur(max(1, int(10 * scale))))
    image.alpha_composite(glow)

    draw = ImageDraw.Draw(image)
    draw.arc(bbox, start=122, end=326, fill=(116, 232, 203, 255), width=int(78 * scale))
    draw.arc(tuple(int(v * scale) for v in (190, 190, 834, 834)), start=132, end=318, fill=(221, 238, 211, 238), width=int(24 * scale))
    draw.arc(bbox, start=319, end=58, fill=(255, 180, 84, 255), width=int(64 * scale))

    outer = tuple(int(v * scale) for v in (300, 300, 724, 724))
    inner = tuple(int(v * scale) for v in (382, 382, 642, 642))
    core = tuple(int(v * scale) for v in (413, 413, 611, 611))
    draw.ellipse(outer, fill=(245, 241, 232, 236))
    draw.ellipse(inner, fill=(5, 7, 6, 255))
    draw.ellipse(core, fill=(2, 4, 3, 255))

    def line(points, color, width):
        draw.line([(int(x * scale), int(y * scale)) for x, y in points], fill=color, width=int(width * scale), joint="curve")

    line([(633, 512), (833, 512)], (255, 180, 84, 255), 30)
    line([(391, 192), (444, 314)], (114, 224, 196, 255), 26)
    line([(286, 739), (398, 662)], (221, 238, 211, 230), 22)
    for cx, cy, r, color in [
        (833, 512, 34, (255, 180, 84, 255)),
        (391, 192, 31, (114, 224, 196, 255)),
        (286, 739, 25, (221, 238, 211, 255)),
    ]:
        draw.ellipse(
            (int((cx - r) * scale), int((cy - r) * scale), int((cx + r) * scale), int((cy + r) * scale)),
            fill=color,
        )

    shine = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shine_draw = ImageDraw.Draw(shine)
    shine_draw.polygon(
        [
            (int(122 * scale), int(122 * scale)),
            (int(708 * scale), int(72 * scale)),
            (int(210 * scale), int(328 * scale)),
        ],
        fill=(255, 255, 255, 22),
    )
    image.alpha_composite(shine)
    image.putalpha(rounded_mask(size, int(216 * scale)))
    return image


def save_png_set() -> None:
    for size in [16, 24, 32, 48, 64, 128, 256, 512, 1024]:
        icon = draw_orbital_icon(size)
        icon.save(BRAND / f"civagent-icon-{size}.png")
    draw_orbital_icon(1024).save(BUILD / "icon.png")
    draw_orbital_icon(256).save(BRAND / "favicon.png")
    draw_orbital_icon(180).save(BRAND / "apple-touch-icon.png")
    draw_orbital_icon(512).save(BRAND / "civagent-icon.png")


def save_ico() -> None:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    icons = [draw_orbital_icon(size) for size in sizes]
    icons[-1].save(BUILD / "icon.ico", sizes=[(size, size) for size in sizes], append_images=icons[:-1])


def save_icns() -> None:
    icon = draw_orbital_icon(1024)
    icon.save(
        BUILD / "icon.icns",
        sizes=[(16, 16), (32, 32), (128, 128), (256, 256), (512, 512), (1024, 1024)],
    )


def main() -> None:
    ensure_dirs()
    save_png_set()
    save_ico()
    save_icns()
    if ICONSET.exists():
        shutil.rmtree(ICONSET)
    print("Generated CivAgent brand icons.")


if __name__ == "__main__":
    main()
