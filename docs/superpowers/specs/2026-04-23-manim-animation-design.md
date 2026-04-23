# Manim Animation Stage — Design Spec
_Date: 2026-04-23_

## Overview

Add a new stage `3b_generate_manim.py` to the video pipeline that generates cinematic animated video clips using Manim, replacing static PNG slides in the final video output.

## Pipeline Changes

```
1  fetch_transcripts   → workspace/transcripts/
2  generate_script     → workspace/scripts/script_en.md
3  generate_slides     → workspace/slides/en/*.png  (kept as fallback)
3b generate_manim      → workspace/manim/en/slide_01.mp4 ...
4  generate_audio      → workspace/audio/en/*.mp3
5  assemble_video      → workspace/output/video_en.mp4
```

Stage 3b is inserted after stage 3 in `run_pipeline.py`. It reads `workspace/slides/slides_en.json` (already produced by stage 3) — no additional API calls required.

## Stage 3b: generate_manim.py

### Input
- `workspace/slides/slides_en.json` — list of `{index, headline, narration}` dicts

### Output
- `workspace/manim/en/slide_01.mp4` … `slide_07.mp4` — 1920×1080 animated clips

### CinematicSlide Scene

Each slide is rendered as a standalone Manim scene at 1920×1080 (60fps). Duration = estimated narration duration + 2s cinematic intro.

**Visual theme:**
- Background: `#12121e` (deep dark)
- Accent colour: `#6366f1` (indigo)
- Headline: white, large, bold
- Bullets: `#c8c8dc`, medium

**Animation phases:**

| Phase | Duration | Content |
|-------|----------|---------|
| Intro | 1–2s | Accent bar slides in from left; headline fades + rises from below; background particles drift upward |
| Bullet reveal | narration duration | 3–4 bullets appear sequentially, timed by word count at 130 wpm |
| Hold | 0.5s | Everything stays on screen |

**Bullet timing formula:**
```
total_seconds = (word_count / 130) * 60
time_per_bullet = total_seconds / num_bullets
```

**Bullet extraction:** Take the first sentence of each paragraph in the narration text. Cap at 4 bullets. Truncate to ≤12 words each for on-screen readability.

### Rendering

Each scene is rendered via `manim render` CLI to a temp directory, then copied to `workspace/manim/en/`. Rendered at 1080p60. If a clip already exists it is skipped (idempotent).

## Stage 5: assemble_video.py Changes

Stage 5 auto-detects which source to use per language:

- If `workspace/manim/{lang}/slide_*.mp4` exists → use Manim clips (video-over-audio ffmpeg concat)
- Otherwise → fall back to PNGs from `workspace/slides/{lang}/` (existing behaviour)

**Manim clip encoding:**
```
ffmpeg -i slide_01.mp4 -i slide_01.mp3 -c:v copy -c:a aac -shortest clip_01.mp4
```

The final concat step is unchanged.

## run_pipeline.py Changes

Stages are renumbered 1–6. `--from-stage` / `--to-stage` range updated to `[1, 6]`.

```python
(1, "Fetch Transcripts", "stages/1_fetch_transcripts.py"),
(2, "Generate Script",   "stages/2_generate_script.py"),
(3, "Generate Slides",   "stages/3_generate_slides.py"),
(4, "Generate Manim",    "stages/3b_generate_manim.py"),
(5, "Generate Audio",    "stages/4_generate_audio.py"),
(6, "Assemble Video",    "stages/5_assemble_video.py"),
```

## Dependencies

- `manim` Python package (`pip install manim`)
- LaTeX not required (text-only scenes use Manim's built-in Cairo renderer)
- ffmpeg (already required by stage 5)

## Error Handling

- If Manim render fails for a slide, log a warning and fall back to the PNG for that slide
- If Manim is not installed, skip stage 3b entirely with a warning (PNG fallback used)
