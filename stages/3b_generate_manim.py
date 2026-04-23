"""
Stage 3b: Generate per-slide cinematic animations using Manim.

Usage:
    python stages/3b_generate_manim.py

Reads:
    workspace/slides/slides_en.json

Outputs:
    workspace/manim/en/slide_01.mp4 ...
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

from generate_manim_helpers import build_scene_code, estimate_duration, extract_bullets


PYTHON = sys.executable


def manim_available() -> bool:
    try:
        subprocess.run([PYTHON, "-m", "manim", "--version"],
                       capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def render_slide(
    index: int,
    headline: str,
    narration: str,
    out_path: str,
) -> bool:
    """
    Render one CinematicSlide to out_path.
    Returns True on success, False on failure.
    """
    bullets = extract_bullets(narration, max_bullets=4)
    duration = estimate_duration(narration)
    code = build_scene_code(headline, bullets, duration)

    with tempfile.TemporaryDirectory() as tmpdir:
        scene_file = os.path.join(tmpdir, f"slide_{index:02d}_scene.py")
        media_dir = os.path.join(tmpdir, "media")
        os.makedirs(media_dir, exist_ok=True)

        with open(scene_file, "w", encoding="utf-8") as f:
            f.write(code)

        result = subprocess.run(
            [
                PYTHON, "-m", "manim", "render",
                "-qh",  # high quality 1080p60
                "--media_dir", media_dir,
                "--disable_caching",
                scene_file,
                "CinematicSlide",
            ],
            capture_output=True,
            text=True,
            cwd=tmpdir,
        )

        if result.returncode != 0:
            print(f"  ERROR rendering slide {index}:\n{result.stderr[-800:]}", file=sys.stderr)
            return False

        # Manim writes to media/videos/<stem>/1080p60/CinematicSlide.mp4
        stem = os.path.splitext(os.path.basename(scene_file))[0]
        pattern = os.path.join(media_dir, "videos", stem, "**", "CinematicSlide.mp4")
        matches = glob.glob(pattern, recursive=True)
        if not matches:
            print(f"  ERROR: could not find rendered output for slide {index}", file=sys.stderr)
            return False

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        shutil.copy2(matches[0], out_path)
        return True


def main():
    parser = argparse.ArgumentParser(description="Generate Manim animated clips per slide")
    parser.add_argument("--slides-dir", default="workspace/slides")
    parser.add_argument("--manim-dir", default="workspace/manim")
    args = parser.parse_args()

    if not manim_available():
        print("[Stage 3b] WARNING: Manim not installed. Skipping animation stage.")
        print("[Stage 3b] Install with: pip install manim")
        sys.exit(0)

    slides_json = os.path.join(args.slides_dir, "slides_en.json")
    if not os.path.exists(slides_json):
        print(f"[Stage 3b] ERROR: {slides_json} not found. Run stage 3 first.", file=sys.stderr)
        sys.exit(1)

    with open(slides_json, encoding="utf-8") as f:
        slides = json.load(f)

    out_dir = os.path.join(args.manim_dir, "en")
    os.makedirs(out_dir, exist_ok=True)
    success = 0

    for slide in slides:
        i = slide["index"]
        out_path = os.path.join(out_dir, f"slide_{i:02d}.mp4")

        if os.path.exists(out_path):
            print(f"  [3b] slide {i:02d} already exists, skipping.")
            success += 1
            continue

        print(f"  [3b] Rendering slide {i}/{len(slides)}: {slide['headline'][:50]}...")
        ok = render_slide(i, slide["headline"], slide["narration"], out_path)
        if ok:
            print(f"    Saved {out_path}")
            success += 1
        else:
            print(f"    WARNING: slide {i} failed — PNG fallback will be used.")

    print(f"[Stage 3b] Done. {success}/{len(slides)} clips rendered.")


if __name__ == "__main__":
    main()
