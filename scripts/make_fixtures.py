"""Generate the test fixtures (sample game-like images) with Pillow.

The images are drawn from scratch - no copyrighted game screenshots are used.

Usage::

    python scripts/make_fixtures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures"

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
    r"C:\Windows\Fonts\tahoma.ttf",
]


def load_font(size: int):
    """Load the first available system font."""
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    return ImageFont.load_default()


def draw_lines(
    draw: ImageDraw.ImageDraw,
    lines,
    origin,
    size: int,
    spacing: int,
) -> None:
    """Draw several lines of text with a per-line colour."""
    font = load_font(size)
    x, y = origin
    for text, color in lines:
        draw.text((x, y), text, font=font, fill=color)
        y += size + spacing


def make_dialogue(path: Path) -> None:
    """(a) 3-line dialogue WITH a speaker name above it."""
    width, height = 1920, 1080
    image = Image.new("RGB", (width, height), (18, 20, 26))
    draw = ImageDraw.Draw(image)
    draw.rectangle([200, 780, 1720, 980], fill=(32, 36, 46), outline=(120, 130, 150))
    draw.text((240, 700), "Jiyan", font=load_font(30), fill=(255, 214, 102))
    draw_lines(
        draw,
        [
            ("The Tacet Field is spreading across the northern plains.", (235, 235, 240)),
            ("Resonators must reach the Storm City before nightfall.", (235, 235, 240)),
            ("You obtained a new Waveplate for your Rover.", (235, 235, 240)),
        ],
        origin=(240, 810),
        size=28,
        spacing=16,
    )
    image.save(path)


def make_quest(path: Path) -> None:
    """(b) quest + skill description."""
    width, height = 1920, 1080
    image = Image.new("RGB", (width, height), (14, 16, 22))
    draw = ImageDraw.Draw(image)
    draw.rectangle([300, 260, 1620, 480], fill=(26, 30, 40), outline=(100, 110, 130))
    draw.text((340, 290), "Quest", font=load_font(34), fill=(255, 214, 102))
    draw_lines(
        draw,
        [
            ("Complete the quest to reach the Storm City", (230, 230, 235)),
            ("before the storm arrives. Reward: 12000", (230, 230, 235)),
        ],
        origin=(340, 350),
        size=26,
        spacing=12,
    )
    draw.rectangle([300, 560, 1620, 820], fill=(22, 26, 34), outline=(100, 110, 130))
    draw.text((340, 590), "Skill", font=load_font(34), fill=(120, 200, 255))
    draw_lines(
        draw,
        [
            ("Your attack power increases by 15 percent", (225, 225, 230)),
            ("when the Havoc attribute is active.", (225, 225, 230)),
        ],
        origin=(340, 650),
        size=26,
        spacing=12,
    )
    image.save(path)


def make_menu(path: Path) -> None:
    """(c) menu + numbers (to test number filtering)."""
    width, height = 1920, 1080
    image = Image.new("RGB", (width, height), (16, 18, 24))
    draw = ImageDraw.Draw(image)
    draw.rectangle([700, 200, 1220, 880], fill=(28, 32, 42), outline=(110, 120, 140))
    font = load_font(30)
    items = [
        ("Inventory", (235, 235, 240)),
        ("1250", (255, 220, 120)),
        ("+8%", (255, 160, 120)),
        ("Lv.30", (255, 220, 120)),
        ("Skills", (235, 235, 240)),
        ("999/999", (255, 160, 120)),
        ("Settings", (235, 235, 240)),
    ]
    y = 240
    for text, color in items:
        draw.text((760, y), text, font=font, fill=color)
        y += 70
    draw.text((100, 950), "12345", font=font, fill=(255, 220, 120))
    image.save(path)


def make_scaled(path: Path) -> None:
    """(d) the dialogue image scaled up to 2560x1600.

    The source is 1920x1080 (16:9) and the target is 2560x1600 (16:10), so the
    image is scaled to fit the width and then padded vertically. That keeps the
    horizontal scale factor exactly 2560/1920 and the vertical one exactly
    1600/1080, which makes it easy to prove that nothing is hardcoded.
    """
    source = FIXTURE_DIR / "sample_a_dialogue.png"
    if not source.exists():
        make_dialogue(source)
    image = Image.open(source).convert("RGB")
    target_w, target_h = 2560, 1600
    scale = target_w / image.width
    new_h = int(round(image.height * scale))
    resized = image.resize((target_w, new_h), Image.LANCZOS)
    canvas = Image.new("RGB", (target_w, target_h), (18, 20, 26))
    canvas.paste(resized, (0, 0))
    canvas.save(path)


def main() -> int:
    """Create all fixtures."""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    make_dialogue(FIXTURE_DIR / "sample_a_dialogue.png")
    make_quest(FIXTURE_DIR / "sample_b_quest.png")
    make_menu(FIXTURE_DIR / "sample_c_menu.png")
    make_scaled(FIXTURE_DIR / "sample_a_dialogue_2560x1600.png")
    for path in sorted(FIXTURE_DIR.glob("*.png")):
        print(f"created {path.name} ({Image.open(path).size})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
