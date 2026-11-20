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


def make_roi_base(path: Path) -> None:
    """(d-1) the reference frame of the ROI test.

    It is the dialogue fixture with a *second* line at the bottom, so the
    "changed" frame only differs in that last line.
    """
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
            ("The first line stays the same in both frames.", (235, 235, 240)),
        ],
        origin=(240, 800),
        size=26,
        spacing=10,
    )
    image.save(path)


def make_roi_changed(path: Path) -> None:
    """(d-2) the same frame as (d-1) with only the last line changed.

    The difference between the two frames is a single line at the bottom of
    the dialogue box, which is exactly the case the ROI OCR has to handle.
    """
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
            ("The last line changed to something completely different.", (240, 200, 120)),
        ],
        origin=(240, 800),
        size=26,
        spacing=10,
    )
    image.save(path)


def make_long_dialogue(path: Path) -> None:
    """(e) a long dialogue that needs to be wrapped inside the bbox."""
    width, height = 1920, 1080
    image = Image.new("RGB", (width, height), (18, 20, 26))
    draw = ImageDraw.Draw(image)
    draw.rectangle([200, 780, 1720, 980], fill=(32, 36, 46), outline=(120, 130, 150))
    draw.text((240, 700), "Shorekeeper", font=load_font(30), fill=(255, 214, 102))
    draw_lines(
        draw,
        [
            (
                "The Shorekeeper has granted you a blessing for the next "
                "expedition into the Tacet Field, and it will protect you.",
                (235, 235, 240),
            ),
        ],
        origin=(240, 810),
        size=28,
        spacing=16,
    )
    image.save(path)


def make_reward_quest(path: Path) -> None:
    """(f) a quest block with the "Reward: 12000" line."""
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
    image.save(path)


def make_ui_menu(path: Path) -> None:
    """(g) a menu with the Quest / Skill / Inventory / Settings labels."""
    width, height = 1920, 1080
    image = Image.new("RGB", (width, height), (16, 18, 24))
    draw = ImageDraw.Draw(image)
    draw.rectangle([700, 200, 1220, 880], fill=(28, 32, 42), outline=(110, 120, 140))
    font = load_font(30)
    items = [
        ("Quest", (255, 214, 102)),
        ("Skill", (255, 214, 102)),
        ("Inventory", (235, 235, 240)),
        ("Settings", (235, 235, 240)),
    ]
    y = 250
    for text, color in items:
        draw.text((760, y), font=font, fill=color, text=text)
        y += 70
    image.save(path)


def make_two_corner_base(path: Path) -> None:
    """(h-1) the reference frame of the two-corner test.

    It is a dialogue scene with a HUD in the top-left corner and a quest
    tracker in the bottom-right corner. The "changed" frame changes the
    text of both of those two corners, so the changed area is made of two
    components that are far apart.
    """
    width, height = 1920, 1080
    image = Image.new("RGB", (width, height), (18, 20, 26))
    draw = ImageDraw.Draw(image)
    draw.rectangle([40, 40, 520, 260], fill=(32, 36, 46), outline=(120, 130, 150))
    draw.text((70, 70), "Inventory", font=load_font(30), fill=(255, 214, 102))
    draw_lines(
        draw,
        [
            ("Waveplate: 12000", (235, 235, 240)),
            ("Astrite: 1500", (235, 235, 240)),
        ],
        origin=(70, 130),
        size=26,
        spacing=14,
    )
    draw.rectangle([1380, 780, 1880, 1040], fill=(32, 36, 46), outline=(120, 130, 150))
    draw.text((1410, 810), "Quest", font=load_font(30), fill=(255, 214, 102))
    draw_lines(
        draw,
        [
            ("Reach the Storm City", (235, 235, 240)),
            ("Reward: 12000", (255, 220, 120)),
        ],
        origin=(1410, 870),
        size=24,
        spacing=14,
    )
    # The dialogue box is drawn BEFORE the bottom-right panel, so the two
    # panels never overlap.
    draw.rectangle([200, 600, 1300, 740], fill=(26, 30, 40), outline=(100, 110, 130))
    draw.text((240, 620), "Jiyan", font=load_font(30), fill=(255, 214, 102))
    draw_lines(
        draw,
        [
            ("The Tacet Field is spreading across the northern plains.", (235, 235, 240)),
            ("Resonators must reach the Storm City before nightfall.", (235, 235, 240)),
        ],
        origin=(240, 670),
        size=28,
        spacing=16,
    )
    image.save(path)


def make_two_corner_changed(path: Path) -> None:
    """(h-2) the same frame with the text of both corners changed.

    The two changed areas are far apart (top-left and bottom-right), so the
    per-region ROI has to read two disjoint rectangles instead of one big
    crop that covers the whole screen.
    """
    width, height = 1920, 1080
    image = Image.new("RGB", (width, height), (18, 20, 26))
    draw = ImageDraw.Draw(image)
    draw.rectangle([40, 40, 520, 260], fill=(32, 36, 46), outline=(120, 130, 150))
    draw.text((70, 70), "Inventory", font=load_font(30), fill=(255, 214, 102))
    # The changed lines of the top-left corner. The whole text is replaced,
    # so every glyph of the line changes (that is what a real dialogue line
    # change looks like).
    draw_lines(
        draw,
        [
            ("Energy: 9999", (255, 160, 120)),
            ("Astrite: 3200", (255, 160, 120)),
        ],
        origin=(70, 130),
        size=26,
        spacing=14,
    )
    draw.rectangle([1380, 780, 1880, 1040], fill=(32, 36, 46), outline=(120, 130, 150))
    draw.text((1410, 810), "Quest", font=load_font(30), fill=(255, 214, 102))
    # The changed lines of the bottom-right corner.
    draw_lines(
        draw,
        [
            ("Go to the harbour", (255, 160, 120)),
            ("Reward: 24000", (255, 160, 120)),
        ],
        origin=(1410, 870),
        size=24,
        spacing=14,
    )
    # The dialogue box is drawn BEFORE the bottom-right panel, so the two
    # panels never overlap.
    draw.rectangle([200, 600, 1300, 740], fill=(26, 30, 40), outline=(100, 110, 130))
    draw.text((240, 620), "Jiyan", font=load_font(30), fill=(255, 214, 102))
    draw_lines(
        draw,
        [
            ("The Tacet Field is spreading across the northern plains.", (235, 235, 240)),
            ("Resonators must reach the Storm City before nightfall.", (235, 235, 240)),
        ],
        origin=(240, 670),
        size=28,
        spacing=16,
    )
    image.save(path)


def make_small_font(path: Path) -> None:
    """(i) the same dialogue with a 0.7x font.

    The layout is the one of fixture (a), but every text is drawn at 70%
    of the normal size. The grouping has to produce the same blocks as the
    normal font, which is what the adaptive grouping (item D) is for.
    """
    width, height = 1920, 1080
    image = Image.new("RGB", (width, height), (18, 20, 26))
    draw = ImageDraw.Draw(image)
    draw.rectangle([200, 780, 1720, 980], fill=(32, 36, 46), outline=(120, 130, 150))
    draw.text((240, 700), "Jiyan", font=load_font(21), fill=(255, 214, 102))
    draw_lines(
        draw,
        [
            ("The Tacet Field is spreading across the northern plains.", (235, 235, 240)),
            ("Resonators must reach the Storm City before nightfall.", (235, 235, 240)),
            ("You obtained a new Waveplate for your Rover.", (235, 235, 240)),
        ],
        # Every position is scaled by 0.7 as well, so the layout of the
        # small font is the layout of the normal font at 70%.
        origin=(240, 777),
        size=20,
        spacing=11,
    )
    image.save(path)


def make_big_change_base(path: Path) -> None:
    """(j-1) the reference frame of the big screen change test.

    It is the plain game view (no menu). The "changed" frame opens a big
    menu that covers a large part of the screen.
    """
    width, height = 1920, 1080
    image = Image.new("RGB", (width, height), (18, 20, 26))
    draw = ImageDraw.Draw(image)
    draw.text((240, 700), "Jiyan", font=load_font(30), fill=(255, 214, 102))
    draw_lines(
        draw,
        [
            ("The Tacet Field is spreading across the northern plains.", (235, 235, 240)),
            ("Resonators must reach the Storm City before nightfall.", (235, 235, 240)),
        ],
        origin=(240, 810),
        size=28,
        spacing=16,
    )
    image.save(path)


def make_big_change_menu(path: Path) -> None:
    """(j-2) the same frame with a big menu opened over the screen.

    The menu covers a large part of the screen, so the changed area is much
    bigger than the "full frame" threshold of the ROI. The tiled refresh has
    to read the changed tiles in parallel and refresh the screen in less
    than 500 ms.
    """
    width, height = 1920, 1080
    image = Image.new("RGB", (width, height), (18, 20, 26))
    draw = ImageDraw.Draw(image)
    draw.rectangle([120, 120, 1800, 960], fill=(28, 32, 42), outline=(120, 130, 150))
    draw.text((180, 170), "Inventory", font=load_font(34), fill=(255, 214, 102))
    draw_lines(
        draw,
        [
            ("Waveplate: 12000", (235, 235, 240)),
            ("Resonance Energy: 4800", (235, 235, 240)),
            ("Astrite: 1500", (235, 235, 240)),
            ("Cost 25 Astrite", (255, 220, 120)),
            ("Press F to equip the item.", (200, 205, 215)),
        ],
        origin=(180, 260),
        size=30,
        spacing=22,
    )
    draw.rectangle([180, 620, 900, 900], fill=(22, 26, 34), outline=(100, 110, 130))
    draw.text((220, 660), "Details", font=load_font(30), fill=(120, 200, 255))
    draw_lines(
        draw,
        [
            ("A rare weapon forged by the Tacet Field.", (225, 225, 230)),
            ("It cannot be traded or sold.", (225, 225, 230)),
        ],
        origin=(220, 720),
        size=26,
        spacing=16,
    )
    draw.text((240, 990), "Esc to close", font=load_font(26), fill=(200, 205, 215))
    image.save(path)


def main() -> int:
    """Create all fixtures."""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    make_dialogue(FIXTURE_DIR / "sample_a_dialogue.png")
    make_quest(FIXTURE_DIR / "sample_b_quest.png")
    make_menu(FIXTURE_DIR / "sample_c_menu.png")
    make_scaled(FIXTURE_DIR / "sample_a_dialogue_2560x1600.png")
    make_roi_base(FIXTURE_DIR / "sample_d_roi_base.png")
    make_roi_changed(FIXTURE_DIR / "sample_d_roi_changed.png")
    make_long_dialogue(FIXTURE_DIR / "sample_e_long.png")
    make_reward_quest(FIXTURE_DIR / "sample_f_reward.png")
    make_ui_menu(FIXTURE_DIR / "sample_g_ui_menu.png")
    # -- the P3 fixtures --------------------------------------------------
    make_two_corner_base(FIXTURE_DIR / "sample_h_two_corner_base.png")
    make_two_corner_changed(FIXTURE_DIR / "sample_h_two_corner_changed.png")
    make_small_font(FIXTURE_DIR / "sample_i_small_font.png")
    make_big_change_base(FIXTURE_DIR / "sample_j_big_change_base.png")
    make_big_change_menu(FIXTURE_DIR / "sample_j_big_change.png")
    for path in sorted(FIXTURE_DIR.glob("*.png")):
        print(f"created {path.name} ({Image.open(path).size})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
