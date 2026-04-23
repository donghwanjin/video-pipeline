"""
Stage 3: Generate slide images from the script files.

Usage:
    python stages/3_generate_slides.py --config config.yaml

Reads:
    workspace/scripts/script_en.md
    workspace/scripts/script_ko.md

Outputs:
    workspace/slides/en/slide_01.png ...
    workspace/slides/ko/slide_01.png ...
    workspace/slides/slides_en.json  (metadata: headline, narration per slide)
    workspace/slides/slides_ko.json
"""

import argparse
import io
import json
import os
import re
import textwrap

from PIL import Image, ImageDraw, ImageFont
import yaml


SLIDE_W, SLIDE_H = 1920, 1080

THEMES = {
    "dark": {
        "bg": (18, 18, 28),
        "accent": (99, 102, 241),   # indigo
        "headline": (255, 255, 255),
        "body": (200, 200, 220),
        "footer": (100, 100, 130),
        "bar_h": 8,
    },
    "light": {
        "bg": (248, 248, 255),
        "accent": (79, 70, 229),
        "headline": (20, 20, 40),
        "body": (60, 60, 80),
        "footer": (150, 150, 180),
        "bar_h": 8,
    },
}


def parse_script(path: str) -> list[dict]:
    """Parse script markdown into list of {section, headline, narration}."""
    with open(path, encoding="utf-8") as f:
        text = f.read()

    slides = []
    # Match ## Slide N: Title blocks
    pattern = re.compile(
        r"##\s+Slide\s+\d+:\s+(.+?)\n"
        r"\*\*Headline:\*\*\s+(.+?)\n"
        r"\*\*Narration:\*\*\s+([\s\S]+?)(?=\n##|\Z)",
        re.MULTILINE,
    )
    for match in pattern.finditer(text):
        section = match.group(1).strip()
        headline = match.group(2).strip()
        narration = match.group(3).strip()
        slides.append({"section": section, "headline": headline, "narration": narration})

    if not slides:
        raise ValueError(f"No slides parsed from {path}. Check script format.")
    return slides


def extract_bullets(narration: str, max_bullets: int = 4) -> list[str]:
    """Extract 3-4 key bullet points from narration text."""
    sentences = re.split(r"(?<=[.!?])\s+", narration.strip())
    # Pick evenly spaced sentences as bullets
    if len(sentences) <= max_bullets:
        bullets = sentences
    else:
        step = len(sentences) / max_bullets
        bullets = [sentences[int(i * step)] for i in range(max_bullets)]
    # Truncate long bullets
    return [s[:120] + "…" if len(s) > 120 else s for s in bullets]


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Try to load a system font, fall back to default."""
    candidates = []
    if bold:
        candidates = [
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    else:
        candidates = [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/calibri.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def render_slide(slide: dict, index: int, total: int, theme: dict, lang: str) -> Image.Image:
    img = Image.new("RGB", (SLIDE_W, SLIDE_H), theme["bg"])
    draw = ImageDraw.Draw(img)

    # Top accent bar
    draw.rectangle([0, 0, SLIDE_W, theme["bar_h"]], fill=theme["accent"])

    # Section label (small, top-left)
    font_section = get_font(28)
    draw.text((80, 40), slide["section"].upper(), font=font_section, fill=theme["accent"])

    # Headline (large, bold)
    font_headline = get_font(72, bold=True)
    headline_y = 120
    # Wrap headline if too long
    wrapped = textwrap.fill(slide["headline"], width=40)
    draw.text((80, headline_y), wrapped, font=font_headline, fill=theme["headline"])

    # Divider line below headline
    line_y = headline_y + 72 * (wrapped.count("\n") + 1) + 20
    draw.rectangle([80, line_y, SLIDE_W - 80, line_y + 3], fill=theme["accent"])

    # Bullet points
    bullets = extract_bullets(slide["narration"])
    font_body = get_font(38)
    bullet_y = line_y + 40
    for bullet in bullets:
        wrapped_bullet = textwrap.fill(bullet, width=75)
        draw.text((110, bullet_y), "•  " + wrapped_bullet, font=font_body, fill=theme["body"])
        bullet_y += 38 * (wrapped_bullet.count("\n") + 1) + 24

    # Footer: slide number + language tag
    font_footer = get_font(26)
    footer_text = f"{lang.upper()}  |  {index} / {total}"
    draw.text((80, SLIDE_H - 60), footer_text, font=font_footer, fill=theme["footer"])

    return img


def generate_slides(script_path: str, out_dir: str, theme_name: str, lang: str):
    theme = THEMES.get(theme_name, THEMES["dark"])
    os.makedirs(out_dir, exist_ok=True)

    slides = parse_script(script_path)
    total = len(slides)
    metadata = []

    for i, slide in enumerate(slides, start=1):
        img = render_slide(slide, i, total, theme, lang)
        out_path = os.path.join(out_dir, f"slide_{i:02d}.png")
        img.save(out_path, "PNG")
        print(f"  Saved {out_path}")
        metadata.append({
            "index": i,
            "section": slide["section"],
            "headline": slide["headline"],
            "narration": slide["narration"],
            "image": out_path,
        })

    meta_path = os.path.join(os.path.dirname(out_dir), f"slides_{lang}.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    print(f"  Metadata saved to {meta_path}")
    return metadata


def main():
    parser = argparse.ArgumentParser(description="Generate slide PNGs from scripts")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--script-dir", default="workspace/scripts")
    parser.add_argument("--slides-dir", default="workspace/slides")
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    theme = cfg.get("slide_theme", "dark")

    print("[Stage 3] Generating English slides...")
    generate_slides(
        os.path.join(args.script_dir, "script_en.md"),
        os.path.join(args.slides_dir, "en"),
        theme,
        "en",
    )

    ko_script = os.path.join(args.script_dir, "script_ko.md")
    if os.path.exists(ko_script):
        try:
            print("[Stage 3] Generating Korean slides...")
            generate_slides(ko_script, os.path.join(args.slides_dir, "ko"), theme, "ko")
        except ValueError as e:
            print(f"[Stage 3] Skipping Korean slides: {e}")
    else:
        print("[Stage 3] Skipping Korean slides (no script found).")

    print("[Stage 3] Done.")


if __name__ == "__main__":
    main()
