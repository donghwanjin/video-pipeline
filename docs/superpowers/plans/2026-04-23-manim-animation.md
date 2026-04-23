# Manim Animation Stage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a cinematic Manim animation stage (3b) to the video pipeline that generates animated MP4 clips per slide, replacing static PNGs in the final video.

**Architecture:** Stage 3b reads `workspace/slides/slides_en.json`, writes a temporary Python scene file per slide (embedding headline/bullets/duration), renders it via the `manim` CLI, and copies the output MP4 to `workspace/manim/en/`. Stage 5 is updated to auto-detect Manim clips and use them instead of PNGs. `run_pipeline.py` is renumbered 1–6 with stage 3b inserted as stage 4.

**Tech Stack:** Python 3.12, Manim CE ≥ 0.18, ffmpeg, existing pipeline (PyYAML, Pillow, Anthropic, ElevenLabs)

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `requirements.txt` | Add `manim>=0.18.0` |
| Create | `stages/3b_generate_manim.py` | Stage 3b: parse slides JSON, write scene files, render via Manim CLI, copy outputs |
| Modify | `stages/5_assemble_video.py` | Auto-detect Manim clips; use video+audio mux instead of image+audio encode |
| Modify | `run_pipeline.py` | Renumber stages 1–6, insert stage 4 (3b) |
| Create | `tests/test_3b_generate_manim.py` | Unit tests for bullet extraction, duration estimation, scene template |

---

## Task 1: Add Manim dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add manim to requirements.txt**

Replace the contents of `requirements.txt` with:

```
anthropic>=0.25.0
youtube-transcript-api>=0.6.2
youtube-comment-downloader>=0.1.68
python-pptx>=0.6.23
Pillow>=10.0.0
elevenlabs>=1.0.0
pyyaml>=6.0
manim>=0.18.0
```

- [ ] **Step 2: Install and verify**

```bash
cd D:/01_Work/video-pipeline
/c/Users/board/AppData/Local/Programs/Python/Python312/python.exe -m pip install manim>=0.18.0
/c/Users/board/AppData/Local/Programs/Python/Python312/python.exe -c "import manim; print(manim.__version__)"
```

Expected: prints a version string like `0.18.1` with no errors.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "feat: add manim dependency"
```

---

## Task 2: Unit tests for pure helper functions

**Files:**
- Create: `tests/test_3b_generate_manim.py`

- [ ] **Step 1: Create the test file**

```python
# tests/test_3b_generate_manim.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "stages"))

import pytest
from generate_manim_helpers import extract_bullets, estimate_duration, build_scene_code


class TestExtractBullets:
    def test_returns_at_most_4_bullets(self):
        narration = "Sentence one. Sentence two. Sentence three. Sentence four. Sentence five. Sentence six."
        bullets = extract_bullets(narration, max_bullets=4)
        assert len(bullets) <= 4

    def test_truncates_long_sentences_to_12_words(self):
        long = "This is a very long sentence that has way more than twelve words in it total."
        bullets = extract_bullets(long, max_bullets=1)
        assert len(bullets[0].split()) <= 13  # 12 words + "..."

    def test_returns_at_least_one_bullet(self):
        bullets = extract_bullets("Just one sentence.", max_bullets=4)
        assert len(bullets) == 1

    def test_empty_narration_returns_empty_list(self):
        bullets = extract_bullets("", max_bullets=4)
        assert bullets == []


class TestEstimateDuration:
    def test_130_words_equals_60_seconds(self):
        narration = " ".join(["word"] * 130)
        assert abs(estimate_duration(narration) - 60.0) < 0.1

    def test_zero_words_returns_zero(self):
        assert estimate_duration("") == 0.0

    def test_65_words_equals_30_seconds(self):
        narration = " ".join(["word"] * 65)
        assert abs(estimate_duration(narration) - 30.0) < 0.1


class TestBuildSceneCode:
    def test_output_is_valid_python(self):
        import ast
        code = build_scene_code(
            headline="Who Were the Picts?",
            bullets=["Bullet one.", "Bullet two."],
            duration=45.0,
        )
        ast.parse(code)  # raises SyntaxError if invalid

    def test_headline_embedded_in_code(self):
        code = build_scene_code("My Headline", [], 10.0)
        assert "My Headline" in code

    def test_special_chars_do_not_break_code(self):
        import ast
        code = build_scene_code('It\'s "complex"', ["Don't stop."], 30.0)
        ast.parse(code)
```

- [ ] **Step 2: Run tests — confirm they fail (module not found)**

```bash
cd D:/01_Work/video-pipeline
/c/Users/board/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/test_3b_generate_manim.py -v
```

Expected: `ModuleNotFoundError: No module named 'stages.generate_manim_helpers'`

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/test_3b_generate_manim.py
git commit -m "test: failing tests for manim helper functions"
```

---

## Task 3: Implement helper module and make tests pass

**Files:**
- Create: `stages/generate_manim_helpers.py`

- [ ] **Step 1: Create `stages/generate_manim_helpers.py`**

```python
"""
Pure helper functions for stage 3b: no Manim or subprocess imports.
Kept separate so they can be unit-tested without Manim installed.
"""
import re
import json


SCENE_TEMPLATE = '''\
from manim import *

ACCENT = ManimColor("#6366f1")
BG = ManimColor("#12121e")
BULLET_COLOR = ManimColor("#c8c8dc")


class CinematicSlide(Scene):
    HEADLINE = {headline}
    BULLETS = {bullets}
    NARRATION_DURATION = {duration}

    def construct(self):
        self.camera.background_color = BG

        # --- Phase 1: Cinematic intro (1.5s) ---
        bar = Rectangle(
            width=config.frame_width + 0.1,
            height=0.12,
            color=ACCENT,
            fill_color=ACCENT,
            fill_opacity=1,
            stroke_width=0,
        )
        bar.to_edge(UP, buff=1.8)
        bar.shift(LEFT * (config.frame_width + 0.1))

        headline = Text(self.HEADLINE, font_size=52, color=WHITE, weight=BOLD)
        headline.to_edge(UP, buff=2.2)
        headline.set_opacity(0)
        self.add(bar, headline)

        self.play(
            bar.animate.shift(RIGHT * (config.frame_width + 0.1)),
            headline.animate.set_opacity(1).shift(UP * 0.3),
            run_time=1.5,
        )
        self.wait(0.3)

        # --- Phase 2: Bullet reveal ---
        y_start = headline.get_bottom()[1] - 0.9
        bullet_rows = []
        for i, bullet_text in enumerate(self.BULLETS):
            dot = Dot(color=ACCENT, radius=0.08)
            text = Text(bullet_text, font_size=34, color=BULLET_COLOR)
            text.next_to(dot, RIGHT, buff=0.25)
            row = VGroup(dot, text)
            row.to_edge(LEFT, buff=1.2)
            row.set_y(y_start - i * 1.0)
            bullet_rows.append(row)

        time_per_bullet = self.NARRATION_DURATION / max(len(bullet_rows), 1)
        for i, row in enumerate(bullet_rows):
            self.play(FadeIn(row, shift=UP * 0.15), run_time=0.5)
            if i < len(bullet_rows) - 1:
                self.wait(max(time_per_bullet - 0.5, 0.1))

        # --- Phase 3: Hold ---
        self.wait(0.5)
'''


def extract_bullets(narration: str, max_bullets: int = 4) -> list[str]:
    """Extract up to max_bullets key sentences from narration text."""
    if not narration.strip():
        return []
    sentences = re.split(r"(?<=[.!?])\s+", narration.strip())
    sentences = [s.strip() for s in sentences if s.strip()]
    step = max(1, len(sentences) // max_bullets)
    selected = sentences[::step][:max_bullets]
    result = []
    for s in selected:
        words = s.split()
        if len(words) > 12:
            s = " ".join(words[:12]) + "..."
        result.append(s)
    return result


def estimate_duration(narration: str) -> float:
    """Estimate narration duration in seconds at 130 words per minute."""
    words = len(narration.split())
    return (words / 130) * 60 if words else 0.0


def build_scene_code(headline: str, bullets: list[str], duration: float) -> str:
    """Return a complete Manim scene Python file as a string."""
    return SCENE_TEMPLATE.format(
        headline=json.dumps(headline),
        bullets=json.dumps(bullets),
        duration=round(duration, 2),
    )
```

- [ ] **Step 2: Run tests — confirm they pass**

```bash
cd D:/01_Work/video-pipeline
/c/Users/board/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/test_3b_generate_manim.py -v
```

Expected: all 10 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add stages/generate_manim_helpers.py
git commit -m "feat: manim helper functions (bullet extraction, duration, scene template)"
```

---

## Task 4: Create stage 3b_generate_manim.py

**Files:**
- Create: `stages/3b_generate_manim.py`

- [ ] **Step 1: Create the stage script**

```python
"""
Stage 3b: Generate per-slide cinematic animations using Manim.

Usage:
    python stages/3b_generate_manim.py --config config.yaml

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
```

- [ ] **Step 2: Do a single-slide smoke test**

First verify `slides_en.json` exists:

```bash
ls D:/01_Work/video-pipeline/workspace/slides/slides_en.json
```

Then run stage 3b:

```bash
cd D:/01_Work/video-pipeline
/c/Users/board/AppData/Local/Programs/Python/Python312/python.exe stages/3b_generate_manim.py
```

Expected: renders 7 clips (or warns if Manim not installed). Clips appear in `workspace/manim/en/`.

- [ ] **Step 3: Commit**

```bash
git add stages/3b_generate_manim.py
git commit -m "feat: stage 3b — cinematic Manim animation per slide"
```

---

## Task 5: Update stage 5 to handle Manim clips

**Files:**
- Modify: `stages/5_assemble_video.py`

- [ ] **Step 1: Add `assemble_lang_manim` function and update `main`**

Add this function after the existing `assemble_lang` function (around line 41), and update `main` to auto-detect:

```python
def assemble_lang_manim(manim_dir: str, audio_dir: str, output_path: str, lang: str):
    """Assemble Manim MP4 clips + MP3 audio into final video."""
    clip_files = sorted(glob.glob(os.path.join(manim_dir, "slide_*.mp4")))
    audio_files = sorted(glob.glob(os.path.join(audio_dir, "slide_*.mp3")))

    if not clip_files:
        raise FileNotFoundError(f"No Manim MP4s found in {manim_dir}")
    if not audio_files:
        raise FileNotFoundError(f"No audio MP3s found in {audio_dir}")
    if len(clip_files) != len(audio_files):
        raise ValueError(
            f"Clip/audio count mismatch: {len(clip_files)} clips, {len(audio_files)} audio"
        )

    muxed_paths = []

    with tempfile.TemporaryDirectory() as tmpdir:
        for i, (clip, audio) in enumerate(zip(clip_files, audio_files), start=1):
            print(f"  [{lang}] Muxing clip {i}/{len(clip_files)}...")
            muxed = os.path.join(tmpdir, f"muxed_{i:02d}.mp4")
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", clip,
                    "-i", audio,
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-shortest",
                    muxed,
                ],
                check=True,
                capture_output=True,
            )
            muxed_paths.append(muxed)

        concat_list = os.path.join(tmpdir, "concat.txt")
        with open(concat_list, "w") as f:
            for path in muxed_paths:
                f.write(f"file '{path}'\n")

        print(f"  [{lang}] Concatenating {len(muxed_paths)} clips into {output_path}...")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_list,
                "-c", "copy",
                output_path,
            ],
            check=True,
            capture_output=True,
        )

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"  [{lang}] Done. Output: {output_path} ({size_mb:.1f} MB)")
```

Then update `main()` in `5_assemble_video.py` — replace the English assembly block:

```python
def main():
    parser = argparse.ArgumentParser(description="Assemble video from slides and audio")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--slides-dir", default="workspace/slides")
    parser.add_argument("--audio-dir", default="workspace/audio")
    parser.add_argument("--manim-dir", default="workspace/manim")
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    output_dir = cfg.get("output_dir", "workspace/output")

    # English — prefer Manim clips over PNGs
    en_manim_dir = os.path.join(args.manim_dir, "en")
    if glob.glob(os.path.join(en_manim_dir, "slide_*.mp4")):
        print("[Stage 5] Assembling English video (Manim clips)...")
        assemble_lang_manim(
            en_manim_dir,
            os.path.join(args.audio_dir, "en"),
            os.path.join(output_dir, "video_en.mp4"),
            "en",
        )
    else:
        print("[Stage 5] Assembling English video (PNG slides)...")
        assemble_lang(
            os.path.join(args.slides_dir, "en"),
            os.path.join(args.audio_dir, "en"),
            os.path.join(output_dir, "video_en.mp4"),
            "en",
        )

    ko_audio_dir = os.path.join(args.audio_dir, "ko")
    if glob.glob(os.path.join(ko_audio_dir, "slide_*.mp3")):
        ko_manim_dir = os.path.join(args.manim_dir, "ko")
        if glob.glob(os.path.join(ko_manim_dir, "slide_*.mp4")):
            print("[Stage 5] Assembling Korean video (Manim clips)...")
            assemble_lang_manim(
                ko_manim_dir,
                ko_audio_dir,
                os.path.join(output_dir, "video_ko.mp4"),
                "ko",
            )
        else:
            print("[Stage 5] Assembling Korean video (PNG slides)...")
            assemble_lang(
                os.path.join(args.slides_dir, "ko"),
                ko_audio_dir,
                os.path.join(output_dir, "video_ko.mp4"),
                "ko",
            )
    else:
        print("[Stage 5] Skipping Korean video (no Korean audio found).")

    print("[Stage 5] Done.")
```

- [ ] **Step 2: Commit**

```bash
git add stages/5_assemble_video.py
git commit -m "feat: stage 5 — auto-detect and use Manim clips when available"
```

---

## Task 6: Update run_pipeline.py (renumber stages 1–6)

**Files:**
- Modify: `run_pipeline.py`

- [ ] **Step 1: Update STAGES list and argument range**

Replace the `STAGES` list and `--from-stage` / `--to-stage` arguments:

```python
STAGES = [
    (1, "Fetch Transcripts", "stages/1_fetch_transcripts.py"),
    (2, "Generate Script",   "stages/2_generate_script.py"),
    (3, "Generate Slides",   "stages/3_generate_slides.py"),
    (4, "Generate Manim",    "stages/3b_generate_manim.py"),
    (5, "Generate Audio",    "stages/4_generate_audio.py"),
    (6, "Assemble Video",    "stages/5_assemble_video.py"),
]
```

And update the `stage_args` dict:

```python
stage_args = {
    1: ["--refs"] + args.refs + ["--out-dir", "workspace/transcripts"],
    2: ["--title", args.title, "--transcript-dir", "workspace/transcripts",
        "--out-dir", "workspace/scripts", "--config", args.config],
    3: ["--config", args.config, "--script-dir", "workspace/scripts",
        "--slides-dir", "workspace/slides"],
    4: ["--slides-dir", "workspace/slides", "--manim-dir", "workspace/manim"],
    5: ["--config", args.config, "--slides-dir", "workspace/slides",
        "--audio-dir", "workspace/audio"],
    6: ["--config", args.config, "--slides-dir", "workspace/slides",
        "--audio-dir", "workspace/audio", "--manim-dir", "workspace/manim"],
}
```

And update the argparse choices:

```python
parser.add_argument(
    "--from-stage", type=int, default=1, choices=[1, 2, 3, 4, 5, 6],
    help="Resume from this stage (skip earlier stages)"
)
parser.add_argument(
    "--to-stage", type=int, default=6, choices=[1, 2, 3, 4, 5, 6],
    help="Stop after this stage"
)
```

- [ ] **Step 2: Verify pipeline runs end-to-end from stage 4**

```bash
cd D:/01_Work/video-pipeline
/c/Users/board/AppData/Local/Programs/Python/Python312/python.exe run_pipeline.py \
  --title "History of Pictish" \
  --refs "https://www.youtube.com/watch?v=bzXRIEQumGE" "https://www.youtube.com/watch?v=0PUj8yYfzv4" \
  --from-stage 4 --to-stage 4
```

Expected: stage 4 (Generate Manim) runs, produces `workspace/manim/en/slide_01.mp4` … `slide_07.mp4`.

- [ ] **Step 3: Commit**

```bash
git add run_pipeline.py
git commit -m "feat: renumber pipeline stages 1-6, add stage 4 (Manim)"
```

---

## Task 7: End-to-end smoke test

- [ ] **Step 1: Run full pipeline from stage 4 through 6**

```bash
cd D:/01_Work/video-pipeline
/c/Users/board/AppData/Local/Programs/Python/Python312/python.exe run_pipeline.py \
  --title "History of Pictish" \
  --refs "https://www.youtube.com/watch?v=bzXRIEQumGE" "https://www.youtube.com/watch?v=0PUj8yYfzv4" \
  --from-stage 4
```

Expected output ends with:
```
[Stage 5] Assembling English video (Manim clips)...
  [en] Done. Output: workspace/output/video_en.mp4 (XX.X MB)
[Stage 5] Done.
PIPELINE COMPLETE
```

- [ ] **Step 2: Verify the output video**

Open `D:/01_Work/video-pipeline/workspace/output/video_en.mp4` in a video player. Confirm:
- Cinematic bar slides in on each slide
- Headline fades in
- Bullets appear one by one during narration
- Audio is present and synced

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: Manim cinematic animation pipeline complete"
```
