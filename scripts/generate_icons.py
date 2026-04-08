#!/usr/bin/env python3
"""Generate sad AWS logo icons (frown instead of smile)."""
import math
import pathlib

import PIL.Image
import PIL.ImageDraw
import PIL.ImageFont

RESOURCES_DIR = pathlib.Path(__file__).parent.parent / "src" / "aws_sso_monitor" / "resources"
AWS_ORANGE = (255, 153, 0)
AWS_DARK = (35, 47, 62)


def _draw_frown(
    draw: PIL.ImageDraw.ImageDraw,
    center: tuple[float, float],
    rx: float,
    ry: float,
    color: tuple[int, ...] | str,
    line_width: int,
) -> None:
    """Draw a frown arc (inverted AWS smile) with arrowhead."""
    cx, cy = center
    bbox = (cx - rx, cy - ry, cx + rx, cy + ry)
    # Arc from 200 to 340 degrees traces the upper portion of the ellipse = frown
    draw.arc(bbox, 200, 340, fill=color, width=line_width)

    # Arrowhead at the 340-degree end
    end_rad = math.radians(340)
    tip_x = cx + rx * math.cos(end_rad)
    tip_y = cy + ry * math.sin(end_rad)

    # Tangent direction (perpendicular to radius, clockwise)
    tangent = end_rad + math.pi / 2
    size = line_width * 2.5
    p1 = (tip_x + size * math.cos(tangent + 0.5), tip_y + size * math.sin(tangent + 0.5))
    p2 = (tip_x + size * math.cos(tangent - 0.5), tip_y + size * math.sin(tangent - 0.5))
    draw.polygon([(tip_x, tip_y), p1, p2], fill=color)


def generate_menubar_icon() -> None:
    """44x44 monochrome template icon for the macOS menu bar."""
    size = 44
    img = PIL.Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = PIL.ImageDraw.Draw(img)

    # "aws" text, small, upper portion
    try:
        font = PIL.ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
    except OSError:
        font = PIL.ImageFont.load_default()
    text_bbox = draw.textbbox((0, 0), "aws", font=font)
    text_w = text_bbox[2] - text_bbox[0]
    draw.text(((size - text_w) / 2, 4), "aws", fill="black", font=font)

    # Frown below text
    _draw_frown(draw, (size / 2, size * 0.72), size * 0.32, size * 0.18, "black", 2)

    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
    img.save(RESOURCES_DIR / "menubar-icon.png")
    print(f"  Created menubar-icon.png ({size}x{size})")


def generate_notification_icon() -> None:
    """256x256 color icon for notifications."""
    size = 256
    img = PIL.Image.new("RGBA", (size, size), (255, 255, 255, 255))
    draw = PIL.ImageDraw.Draw(img)

    # "aws" text, large, centered upper portion
    try:
        font = PIL.ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 72)
    except OSError:
        font = PIL.ImageFont.load_default(72)
    text_bbox = draw.textbbox((0, 0), "aws", font=font)
    text_w = text_bbox[2] - text_bbox[0]
    draw.text(((size - text_w) / 2, size * 0.12), "aws", fill=AWS_DARK, font=font)

    # Orange frown
    _draw_frown(draw, (size / 2, size * 0.72), size * 0.3, size * 0.13, AWS_ORANGE, 8)

    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
    img.save(RESOURCES_DIR / "notification-icon.png")
    print(f"  Created notification-icon.png ({size}x{size})")


if __name__ == "__main__":
    print("Generating sad AWS icons...")
    generate_menubar_icon()
    generate_notification_icon()
    print(f"Done. Icons in {RESOURCES_DIR}")
