# AI Image Generation Stage — Design Spec
_Date: 2026-04-23_

## Overview

Add a new stage `3c_generate_images.py` that generates 5–8 AI images per video using Flux (via Replicate) and appends them as a cinematic outro gallery at the end of the final video.

## Pipeline Changes

```
1  fetch_transcripts   → workspace/transcripts/
2  generate_script     → workspace/scripts/script_en.md
3  generate_slides     → workspace/slides/en/*.png
4  generate_manim      → workspace/manim/en/slide_*.mp4
5  generate_images     → workspace/images/en/image_01.png … image_N.png  ← NEW
6  generate_audio      → workspace/audio/en/*.mp3
7  assemble_video      → workspace/output/video_en.mp4 (+ outro gallery)
```

Stages renumbered 1–7. `--from-stage` / `--to-stage` choices updated to `[1, 7]`.

## config.yaml Changes

Two new fields added:

```yaml
replicate_api_key: "r8_..."
image_count: 6          # number of AI images to generate (5–8 recommended)
```

## Stage 5: generate_images.py

### Input
- `workspace/scripts/script_en.md` — full English script

### Output
- `workspace/images/en/prompts.json` — list of image prompts (inspect/edit before generation)
- `workspace/images/en/image_01.png` … `image_N.png` — 1920×1080 generated images

### Step 1: Prompt Generation (Claude API)

Stage 5 reads `script_en.md` and calls the Claude API (`claude-haiku-4-5-20251001`) with instructions to produce `image_count` cinematic image prompts. Each prompt targets a different key visual moment from the video.

**Prompt rules sent to Claude:**
- One prompt per key topic/moment in the video
- Visually evocative, cinematic, no text or UI elements
- Dark, dramatic aesthetic matching the video theme
- Suitable for a 1920×1080 widescreen image

Prompts are saved to `workspace/images/en/prompts.json` for inspection before generation.

### Step 2: Image Generation (Flux via Replicate)

Each prompt is sent to `black-forest-labs/flux-schnell` on Replicate at 1920×1080 resolution. Images are downloaded and saved as PNG files.

- Already-generated images are skipped (idempotent)
- Cost: ~$0.003 per image
- `replicate_api_key` read from `config.yaml`

## Stage 7: assemble_video.py Changes

After assembling the main video, stage 7 checks for `workspace/images/en/image_*.png`. If found, it appends an outro gallery:

**Gallery structure:**
- Each image displayed for `10 / image_count` seconds (e.g. 6 images → ~1.67s each)
- Subtle Ken Burns effect (slow zoom-in) via ffmpeg `zoompan` filter
- No narration — silent (ready for music layer later)
- ffmpeg concatenates gallery clips onto the end of the main video

**Backwards compatible:** if no images are found, assembly proceeds exactly as before.

**Output:** `workspace/output/video_en.mp4` — same file, extended with the outro.

## Error Handling

- If `replicate_api_key` is missing or `"r8_..."`, skip image generation with a warning
- If a single image generation fails, log a warning and continue with remaining images
- If fewer than 2 images are available, skip the outro gallery entirely

## Dependencies

- `replicate` Python package (`pip install replicate`)
- `anthropic` (already in requirements)
- `ffmpeg` (already required)
