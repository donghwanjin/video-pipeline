# Stock Footage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace a configurable number of slides with Pexels stock video clips chosen by Claude, layered with original narration audio.

**Architecture:** A new Stage 3e (`stages/3e_generate_stock.py`) sits between image generation (3c) and SFX (3d). It calls Claude to select `stock_count` slide indices + search keywords, then downloads matching MP4 clips from Pexels into `workspace/stock/`. Assembly (`5_assemble_video.py`) substitutes stock clips for tagged slides during base video construction, trimming or padding each clip to match its narration audio duration.

**Tech Stack:** Python 3.12, Anthropic SDK (`claude-haiku-4-5-20251001`), `requests` (Pexels REST API), `ffmpeg`/`ffprobe` (clip trim/pad/scale), `pytest` (unit tests)

---

## File Structure

| File | Change | Responsibility |
|------|--------|----------------|
| `stages/generate_stock_helpers.py` | CREATE | Pure helpers: `build_stock_prompt`, `parse_cues`, `build_pexels_url` |
| `tests/test_generate_stock_helpers.py` | CREATE | Unit tests for all helpers (13 tests) |
| `stages/3e_generate_stock.py` | CREATE | Stage 3e: Claude cue generation + Pexels download |
| `stages/5_assemble_video.py` | MODIFY | Add `substitute_stock_clip()`, thread `stock_dir` through `assemble_lang()` and `assemble_lang_manim()` |
| `run_pipeline.py` | MODIFY | Insert stage 6 (stock), renumber SFX→7, audio→8, assemble→9; add `--stock-dir` to stage 9 args |
| `config.example.yaml` | MODIFY | Add `pexels_api_key`, `stock_count` |

---

## Task 1: generate_stock_helpers.py + tests

**Files:**
- Create: `stages/generate_stock_helpers.py`
- Create: `tests/test_generate_stock_helpers.py`

- [ ] **Step 1: Create the test file**

```python
# tests/test_generate_stock_helpers.py
import sys
import json
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "stages"))
from generate_stock_helpers import build_stock_prompt, parse_cues, build_pexels_url


class TestBuildStockPrompt:
    def test_returns_string(self):
        result = build_stock_prompt("A script about ancient history.", 3)
        assert isinstance(result, str)

    def test_contains_stock_count(self):
        result = build_stock_prompt("Some script text.", 4)
        assert "4" in result

    def test_contains_script_excerpt(self):
        script = "The Colosseum was built in Rome."
        result = build_stock_prompt(script, 3)
        assert "Colosseum" in result

    def test_specifies_json_output(self):
        result = build_stock_prompt("Script text.", 3)
        assert "JSON" in result

    def test_specifies_slide_index_and_keyword(self):
        result = build_stock_prompt("Script text.", 3)
        assert "slide_index" in result
        assert "keyword" in result


class TestParseCues:
    def test_parses_plain_json_array(self):
        response = json.dumps([{"slide_index": 1, "keyword": "roman forum"}])
        result = parse_cues(response, 3)
        assert result == [{"slide_index": 1, "keyword": "roman forum"}]

    def test_extracts_json_from_markdown_block(self):
        response = '```json\n[{"slide_index": 2, "keyword": "castle ruins"}]\n```'
        result = parse_cues(response, 3)
        assert result == [{"slide_index": 2, "keyword": "castle ruins"}]

    def test_truncates_to_stock_count(self):
        items = [{"slide_index": i, "keyword": f"keyword {i}"} for i in range(1, 6)]
        response = json.dumps(items)
        result = parse_cues(response, 3)
        assert len(result) == 3

    def test_raises_on_empty_array(self):
        with pytest.raises(ValueError, match="No cues"):
            parse_cues("[]", 3)

    def test_raises_on_non_list_json(self):
        with pytest.raises(ValueError, match="Expected JSON array"):
            parse_cues('{"slide_index": 1, "keyword": "test"}', 3)

    def test_raises_on_malformed_json(self):
        with pytest.raises(ValueError, match="not valid JSON"):
            parse_cues("not json at all", 3)

    def test_strips_whitespace_from_keyword(self):
        response = json.dumps([{"slide_index": 1, "keyword": "  roman ruins  "}])
        result = parse_cues(response, 3)
        assert result[0]["keyword"] == "roman ruins"

    def test_skips_entries_missing_required_fields(self):
        response = json.dumps([
            {"slide_index": 1},
            {"keyword": "test"},
            {"slide_index": 2, "keyword": "valid entry"},
        ])
        result = parse_cues(response, 3)
        assert result == [{"slide_index": 2, "keyword": "valid entry"}]

    def test_raises_when_all_entries_invalid(self):
        response = json.dumps([{"bad": "entry"}, {"also": "bad"}])
        with pytest.raises(ValueError, match="No valid cues"):
            parse_cues(response, 3)


class TestBuildPexelsUrl:
    def test_encodes_spaces_as_plus(self):
        url = build_pexels_url("ancient roman forum")
        assert "ancient+roman+forum" in url

    def test_includes_keyword(self):
        url = build_pexels_url("castle ruins")
        assert "castle+ruins" in url or "castle%20ruins" in url

    def test_targets_pexels(self):
        url = build_pexels_url("test")
        assert "api.pexels.com" in url
```

- [ ] **Step 2: Run tests to confirm they fail**

```
cd D:\01_Work\video-pipeline
pytest tests/test_generate_stock_helpers.py -v
```

Expected: `ERROR` — `ModuleNotFoundError: No module named 'generate_stock_helpers'`

- [ ] **Step 3: Create the helpers module**

```python
# stages/generate_stock_helpers.py
"""
Pure helper functions for the stock footage generation stage.
No I/O, no API calls — only string manipulation and parsing.
"""

import json
import re
import urllib.parse


def build_stock_prompt(script_text: str, stock_count: int) -> str:
    """
    Build the user message sent to Claude to generate stock footage cues.

    Args:
        script_text: Full text of the video script (script_en.md content).
        stock_count: Number of stock footage cues to request.

    Returns:
        A formatted string ready to send as a Claude user message.
    """
    return (
        f"You are a video producer. Read the video script below and pick exactly "
        f"{stock_count} moments where real-world stock footage would enhance the content.\n\n"
        f"For each moment, provide:\n"
        f"- slide_index: the slide number (1-based integer) where stock footage should replace the slide\n"
        f'- keyword: a short Pexels video search phrase (2-5 words, e.g. "ancient roman ruins")\n\n'
        f"Pick visually rich moments that benefit from real-world footage — establishing shots, "
        f"cultural scenes, natural phenomena, historical locations.\n\n"
        f"Return ONLY a JSON array with no explanation:\n"
        f'[{{"slide_index": 2, "keyword": "ancient roman forum"}}, '
        f'{{"slide_index": 5, "keyword": "medieval castle ruins"}}]\n\n'
        f"Script:\n{script_text}"
    )


def parse_cues(response_text: str, stock_count: int) -> list[dict]:
    """
    Extract stock footage cues from Claude's response text.

    Handles plain JSON arrays and JSON embedded in markdown code blocks.
    Skips entries that are not dicts or are missing required fields.

    Args:
        response_text: Raw text returned by Claude.
        stock_count: Maximum number of cues to return.

    Returns:
        List of dicts with 'slide_index' (int) and 'keyword' (str), up to stock_count.

    Raises:
        ValueError: If no valid cues could be parsed.
    """
    text = response_text.strip()

    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Claude response is not valid JSON: {exc}") from exc
    if not isinstance(raw, list):
        raise ValueError(f"Expected JSON array from Claude, got {type(raw).__name__}")
    if not raw:
        raise ValueError("No cues parsed from Claude response")

    cues = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        slide_index = item.get("slide_index")
        keyword = str(item.get("keyword", "")).strip()
        if not isinstance(slide_index, int) or not keyword:
            continue
        cues.append({"slide_index": slide_index, "keyword": keyword})

    if not cues:
        raise ValueError("No valid cues parsed from Claude response")

    return cues[:stock_count]


def build_pexels_url(keyword: str) -> str:
    """
    Build a Pexels video search URL for the given keyword.

    Args:
        keyword: Search term (e.g. "ancient roman forum").

    Returns:
        Full URL string for the Pexels video search API.
    """
    encoded = urllib.parse.quote_plus(keyword)
    return (
        f"https://api.pexels.com/videos/search"
        f"?query={encoded}&per_page=5&orientation=landscape"
    )
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_generate_stock_helpers.py -v
```

Expected: `13 passed`

- [ ] **Step 5: Commit**

```bash
git add stages/generate_stock_helpers.py tests/test_generate_stock_helpers.py
git commit -m "feat: add generate_stock_helpers with tests"
```

---

## Task 2: 3e_generate_stock.py (Claude cues + Pexels download)

**Files:**
- Create: `stages/3e_generate_stock.py`

This stage mirrors `stages/3d_generate_sfx.py` exactly, but calls Pexels instead of Freesound and downloads MP4 clips instead of MP3 previews.

- [ ] **Step 1: Create the stage file**

```python
# stages/3e_generate_stock.py
"""
Stage 3e: Generate stock footage cues using Claude, then download from Pexels.

Usage:
    python stages/3e_generate_stock.py --config config.yaml

Reads:
    workspace/scripts/script_en.md

Outputs:
    workspace/stock/stock_cues.json
    workspace/stock/slide_03.mp4, slide_07.mp4, ...  (one per cue)
"""

import argparse
import json
import os
import sys

import anthropic
import requests
import yaml

sys.path.insert(0, os.path.dirname(__file__))
from generate_stock_helpers import build_stock_prompt, parse_cues, build_pexels_url

CLAUDE_MODEL = "claude-haiku-4-5-20251001"
PEXELS_PLACEHOLDER = "your_pexels_key_here"


def _load_config(config_path: str) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def generate_cues(script_text: str, stock_count: int, anthropic_key: str) -> list[dict]:
    """Call Claude to generate stock_count stock footage cues from the script."""
    client = anthropic.Anthropic(api_key=anthropic_key)
    user_message = build_stock_prompt(script_text, stock_count)
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": user_message}],
    )
    return parse_cues(response.content[0].text, stock_count)


def search_pexels(keyword: str, api_key: str) -> str | None:
    """
    Search Pexels for a video clip matching keyword.

    Returns the HD video file URL (fallback to SD) for the first result.
    Returns None if no results or request fails.
    """
    url = build_pexels_url(keyword)
    try:
        resp = requests.get(url, headers={"Authorization": api_key}, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  WARNING: Pexels search failed for '{keyword}': {exc}", file=sys.stderr)
        return None
    videos = resp.json().get("videos", [])
    if not videos:
        return None
    video_files = videos[0].get("video_files", [])
    hd_file = next((f for f in video_files if f.get("quality") == "hd"), None)
    sd_file = next((f for f in video_files if f.get("quality") == "sd"), None)
    chosen = hd_file or sd_file
    return chosen.get("link") if chosen else None


def download_clip(url: str, output_path: str) -> bool:
    """Download MP4 clip from URL to output_path. Returns True on success."""
    try:
        resp = requests.get(url, timeout=60, stream=True)
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except requests.RequestException as exc:
        print(f"  WARNING: Clip download failed: {exc}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Generate stock footage cues and download clips"
    )
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--script-dir", default="workspace/scripts")
    parser.add_argument("--stock-dir", default="workspace/stock")
    args = parser.parse_args()

    cfg = _load_config(args.config)

    pexels_key = cfg.get("pexels_api_key", PEXELS_PLACEHOLDER)
    if not pexels_key or pexels_key == PEXELS_PLACEHOLDER:
        print("[Stage 3e] WARNING: pexels_api_key not set. Skipping stock footage generation.")
        return

    anthropic_key = cfg.get("anthropic_api_key", "")
    if not anthropic_key or anthropic_key.startswith("sk-ant-..."):
        print("[Stage 3e] ERROR: anthropic_api_key not set in config.", file=sys.stderr)
        sys.exit(1)

    stock_count = int(cfg.get("stock_count", 3))

    script_path = os.path.join(args.script_dir, "script_en.md")
    if not os.path.exists(script_path):
        print(f"[Stage 3e] ERROR: script not found: {script_path}", file=sys.stderr)
        sys.exit(1)

    with open(script_path, encoding="utf-8") as f:
        script_text = f.read()

    os.makedirs(args.stock_dir, exist_ok=True)

    # Step 1: Generate cues (idempotent — skip if stock_cues.json already exists)
    cues_path = os.path.join(args.stock_dir, "stock_cues.json")
    if os.path.exists(cues_path):
        print(f"[Stage 3e] Loading existing cues from {cues_path}")
        with open(cues_path, encoding="utf-8") as f:
            cues = json.load(f)
    else:
        print(f"[Stage 3e] Generating {stock_count} stock footage cues via Claude...")
        cues = generate_cues(script_text, stock_count, anthropic_key)
        with open(cues_path, "w", encoding="utf-8") as f:
            json.dump(cues, f, indent=2, ensure_ascii=False)
        print(f"[Stage 3e] Cues saved to {cues_path}")

    # Step 2: Download clips (idempotent — skip individual file if already downloaded)
    downloaded = 0
    for cue in cues:
        slide_index = cue["slide_index"]
        keyword = cue["keyword"]
        out_path = os.path.join(args.stock_dir, f"slide_{slide_index:02d}.mp4")

        if os.path.exists(out_path):
            print(f"[Stage 3e] Skipping slide {slide_index} clip (already exists)")
            downloaded += 1
            continue

        print(f"[Stage 3e] Searching Pexels for '{keyword}' (slide {slide_index})...")
        clip_url = search_pexels(keyword, pexels_key)
        if not clip_url:
            print(f"  WARNING: No Pexels results for '{keyword}'. Skipping.", file=sys.stderr)
            continue

        if download_clip(clip_url, out_path):
            size_mb = os.path.getsize(out_path) / (1024 * 1024)
            print(f"[Stage 3e]   Saved {out_path} ({size_mb:.1f} MB)")
            downloaded += 1

    print(
        f"[Stage 3e] Done. {downloaded}/{len(cues)} clips available in {args.stock_dir}"
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-test the module imports correctly**

```
cd D:\01_Work\video-pipeline
python -c "import stages.generate_stock_helpers; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Run full test suite to confirm no regressions**

```
pytest tests/ -v
```

Expected: all existing tests pass + 13 new stock helper tests pass

- [ ] **Step 4: Commit**

```bash
git add stages/3e_generate_stock.py
git commit -m "feat: add stage 3e — stock footage cue generation and Pexels download"
```

---

## Task 3: substitute_stock_clip() + assembly integration

**Files:**
- Modify: `stages/5_assemble_video.py`

Add `substitute_stock_clip()` and thread `stock_dir` through both assembly functions. No new tests (function uses ffmpeg subprocess; tested via integration).

The current `assemble_lang` and `assemble_lang_manim` functions encode every slide the same way. This task adds a `stock_dir` parameter to both. Before encoding each slide, if a stock clip exists for that slide index, use it instead.

- [ ] **Step 1: Read the current assemble_lang function** (lines 43–110 of `stages/5_assemble_video.py`)

Confirm the inner loop starts at line ~58: `for i, (slide, audio) in enumerate(zip(slide_files, audio_files), start=1):`

- [ ] **Step 2: Add `substitute_stock_clip()` function**

Insert the following function immediately before the `assemble_lang` function (before line 43):

```python
def substitute_stock_clip(
    slide_index: int,
    stock_dir: str,
    audio_path: str,
    output_path: str,
) -> bool:
    """
    Replace a slide with a stock video clip trimmed/padded to match narration audio duration.

    Scales clip to 1920x1080, pads shorter clips with a frozen last frame,
    trims longer clips to the exact narration length.

    Args:
        slide_index: 1-based slide index (matches stock filename slide_NN.mp4).
        stock_dir: Directory containing stock clips (slide_NN.mp4 files).
        audio_path: Path to the narration MP3 for this slide (determines duration).
        output_path: Where to write the resulting MP4 clip.

    Returns:
        True if the stock clip was used, False if no stock clip is available for this slide.
    """
    stock_path = os.path.join(stock_dir, f"slide_{slide_index:02d}.mp4")
    if not os.path.exists(stock_path):
        return False

    duration = get_audio_duration(audio_path)

    try:
        clip_duration = get_audio_duration(stock_path)
    except Exception as exc:
        print(f"  [stock] WARNING: could not read duration of {stock_path}: {exc}")
        return False

    gap = max(0.0, duration - clip_duration)
    scale_filter = (
        "scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
    )
    pad_filter = f"tpad=stop_mode=clone:stop_duration={gap:.3f}"
    vf = f"{scale_filter},{pad_filter}"

    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", stock_path,
                "-i", audio_path,
                "-vf", vf,
                "-map", "0:v",
                "-map", "1:a",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-t", str(duration),
                output_path,
            ],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        print(
            f"  [stock] WARNING: ffmpeg failed for slide {slide_index}: "
            f"{exc.stderr.decode(errors='replace')}",
            file=sys.stderr,
        )
        return False

    return True
```

- [ ] **Step 3: Modify `assemble_lang` to accept and use `stock_dir`**

Replace the current `assemble_lang` signature and inner loop:

**Old signature (line 43):**
```python
def assemble_lang(slides_dir: str, audio_dir: str, output_path: str, lang: str):
```

**New signature:**
```python
def assemble_lang(slides_dir: str, audio_dir: str, output_path: str, lang: str, stock_dir: str = ""):
```

**Old inner loop body (inside `with tempfile.TemporaryDirectory() as tmpdir:`, lines ~59–86):**
```python
        for i, (slide, audio) in enumerate(zip(slide_files, audio_files), start=1):
            print(f"  [{lang}] Encoding clip {i}/{len(slide_files)}...")
            duration = get_audio_duration(audio)
            clip_path = os.path.join(tmpdir, f"clip_{i:02d}.mp4")

            # Encode one clip: hold the image for audio duration, fade in/out
            fade_dur = min(0.3, duration / 4)
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-loop", "1",
                    "-i", slide,
                    "-i", audio,
                    "-c:v", "libx264",
                    "-tune", "stillimage",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-pix_fmt", "yuv420p",
                    "-t", str(duration),
                    "-vf", f"fade=t=in:st=0:d={fade_dur},fade=t=out:st={duration - fade_dur}:d={fade_dur}",
                    "-af", f"afade=t=in:st=0:d={fade_dur},afade=t=out:st={duration - fade_dur}:d={fade_dur}",
                    "-shortest",
                    clip_path,
                ],
                check=True,
                capture_output=True,
            )
            clip_paths.append(clip_path)
```

**New inner loop body:**
```python
        for i, (slide, audio) in enumerate(zip(slide_files, audio_files), start=1):
            print(f"  [{lang}] Encoding clip {i}/{len(slide_files)}...")
            clip_path = os.path.join(tmpdir, f"clip_{i:02d}.mp4")

            # Try stock substitution first
            if stock_dir and substitute_stock_clip(i, stock_dir, audio, clip_path):
                print(f"  [{lang}]   Using stock clip for slide {i}")
                clip_paths.append(clip_path)
                continue

            # Normal PNG encoding: hold the image for audio duration, fade in/out
            duration = get_audio_duration(audio)
            fade_dur = min(0.3, duration / 4)
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-loop", "1",
                    "-i", slide,
                    "-i", audio,
                    "-c:v", "libx264",
                    "-tune", "stillimage",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-pix_fmt", "yuv420p",
                    "-t", str(duration),
                    "-vf", f"fade=t=in:st=0:d={fade_dur},fade=t=out:st={duration - fade_dur}:d={fade_dur}",
                    "-af", f"afade=t=in:st=0:d={fade_dur},afade=t=out:st={duration - fade_dur}:d={fade_dur}",
                    "-shortest",
                    clip_path,
                ],
                check=True,
                capture_output=True,
            )
            clip_paths.append(clip_path)
```

- [ ] **Step 4: Modify `assemble_lang_manim` to accept and use `stock_dir`**

**Old signature (line 113):**
```python
def assemble_lang_manim(manim_dir: str, audio_dir: str, output_path: str, lang: str):
```

**New signature:**
```python
def assemble_lang_manim(manim_dir: str, audio_dir: str, output_path: str, lang: str, stock_dir: str = ""):
```

**Old inner loop body (lines ~130–147):**
```python
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
```

**New inner loop body:**
```python
        for i, (clip, audio) in enumerate(zip(clip_files, audio_files), start=1):
            print(f"  [{lang}] Muxing clip {i}/{len(clip_files)}...")
            muxed = os.path.join(tmpdir, f"muxed_{i:02d}.mp4")

            # Try stock substitution first
            if stock_dir and substitute_stock_clip(i, stock_dir, audio, muxed):
                print(f"  [{lang}]   Using stock clip for slide {i}")
                muxed_paths.append(muxed)
                continue

            # Normal Manim mux
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
```

- [ ] **Step 5: Add `--stock-dir` argument to `main()` and pass it through**

In `main()`, add the argument after the existing `--sfx-dir` line:

**Find (line ~389):**
```python
    parser.add_argument("--sfx-dir", default="workspace/sfx")
```

**Add after it:**
```python
    parser.add_argument("--stock-dir", default="workspace/stock")
```

Then update both assembly call sites in `main()` to pass `stock_dir=args.stock_dir`:

**Old English Manim call (line ~400):**
```python
        assemble_lang_manim(
            en_manim_dir,
            os.path.join(args.audio_dir, "en"),
            os.path.join(output_dir, "video_en.mp4"),
            "en",
        )
```

**New:**
```python
        assemble_lang_manim(
            en_manim_dir,
            os.path.join(args.audio_dir, "en"),
            os.path.join(output_dir, "video_en.mp4"),
            "en",
            stock_dir=args.stock_dir,
        )
```

**Old English PNG call (line ~406):**
```python
        assemble_lang(
            os.path.join(args.slides_dir, "en"),
            os.path.join(args.audio_dir, "en"),
            os.path.join(output_dir, "video_en.mp4"),
            "en",
        )
```

**New:**
```python
        assemble_lang(
            os.path.join(args.slides_dir, "en"),
            os.path.join(args.audio_dir, "en"),
            os.path.join(output_dir, "video_en.mp4"),
            "en",
            stock_dir=args.stock_dir,
        )
```

Korean assembly calls do NOT get `stock_dir` (stock substitution is English-only, matching SFX scoping). Leave the Korean `assemble_lang_manim` and `assemble_lang` calls unchanged.

- [ ] **Step 6: Run full test suite**

```
cd D:\01_Work\video-pipeline
pytest tests/ -v
```

Expected: all tests pass (no regressions)

- [ ] **Step 7: Commit**

```bash
git add stages/5_assemble_video.py
git commit -m "feat: add substitute_stock_clip and thread stock_dir through assembly"
```

---

## Task 4: run_pipeline.py renumbering + config + requirements

**Files:**
- Modify: `run_pipeline.py`
- Modify: `config.example.yaml`

No tests — config and orchestration wiring only.

The current pipeline has 8 stages (1–8). Inserting stock footage between images (stage 5) and SFX (stage 6) requires renumbering: stock becomes 6, SFX becomes 7, audio becomes 8, assemble becomes 9.

- [ ] **Step 1: Update `run_pipeline.py` module docstring**

**Old docstring stages section:**
```python
Stages:
    1  fetch_transcripts
    2  generate_script
    3  generate_slides
    4  generate_manim     (cinematic Manim animations)
    5  generate_images    (AI images via Flux for outro gallery)
    6  generate_sfx       (Claude SFX cues + Freesound download)
    7  generate_audio
    8  assemble_video     (appends SFX mix + AI image outro if available)
```

**New:**
```python
Stages:
    1  fetch_transcripts
    2  generate_script
    3  generate_slides
    4  generate_manim     (cinematic Manim animations)
    5  generate_images    (AI images via Flux for outro gallery)
    6  generate_stock     (Claude stock cues + Pexels download)
    7  generate_sfx       (Claude SFX cues + Freesound download)
    8  generate_audio
    9  assemble_video     (stock substitution + SFX mix + AI image outro)
```

- [ ] **Step 2: Update the `STAGES` list**

**Old:**
```python
STAGES = [
    (1, "Fetch Transcripts", "stages/1_fetch_transcripts.py"),
    (2, "Generate Script",   "stages/2_generate_script.py"),
    (3, "Generate Slides",   "stages/3_generate_slides.py"),
    (4, "Generate Manim",    "stages/3b_generate_manim.py"),
    (5, "Generate Images",   "stages/3c_generate_images.py"),
    (6, "Generate SFX",      "stages/3d_generate_sfx.py"),
    (7, "Generate Audio",    "stages/4_generate_audio.py"),
    (8, "Assemble Video",    "stages/5_assemble_video.py"),
]
```

**New:**
```python
STAGES = [
    (1, "Fetch Transcripts", "stages/1_fetch_transcripts.py"),
    (2, "Generate Script",   "stages/2_generate_script.py"),
    (3, "Generate Slides",   "stages/3_generate_slides.py"),
    (4, "Generate Manim",    "stages/3b_generate_manim.py"),
    (5, "Generate Images",   "stages/3c_generate_images.py"),
    (6, "Generate Stock",    "stages/3e_generate_stock.py"),
    (7, "Generate SFX",      "stages/3d_generate_sfx.py"),
    (8, "Generate Audio",    "stages/4_generate_audio.py"),
    (9, "Assemble Video",    "stages/5_assemble_video.py"),
]
```

- [ ] **Step 3: Update `--from-stage` and `--to-stage` choices + default**

**Old:**
```python
    parser.add_argument(
        "--from-stage", type=int, default=1, choices=[1, 2, 3, 4, 5, 6, 7, 8],
        help="Resume from this stage (skip earlier stages)"
    )
    parser.add_argument(
        "--to-stage", type=int, default=8, choices=[1, 2, 3, 4, 5, 6, 7, 8],
        help="Stop after this stage"
    )
```

**New:**
```python
    parser.add_argument(
        "--from-stage", type=int, default=1, choices=[1, 2, 3, 4, 5, 6, 7, 8, 9],
        help="Resume from this stage (skip earlier stages)"
    )
    parser.add_argument(
        "--to-stage", type=int, default=9, choices=[1, 2, 3, 4, 5, 6, 7, 8, 9],
        help="Stop after this stage"
    )
```

- [ ] **Step 4: Update the `stage_args` dict**

**Old:**
```python
    stage_args = {
        1: ["--refs"] + args.refs + ["--out-dir", "workspace/transcripts"],
        2: ["--title", args.title, "--transcript-dir", "workspace/transcripts",
            "--out-dir", "workspace/scripts", "--config", args.config],
        3: ["--config", args.config, "--script-dir", "workspace/scripts",
            "--slides-dir", "workspace/slides"],
        4: ["--slides-dir", "workspace/slides", "--manim-dir", "workspace/manim"],
        5: ["--config", args.config, "--script-dir", "workspace/scripts",
            "--images-dir", "workspace/images"],
        6: ["--config", args.config, "--script-dir", "workspace/scripts",
            "--sfx-dir", "workspace/sfx"],
        7: ["--config", args.config, "--slides-dir", "workspace/slides",
            "--audio-dir", "workspace/audio"],
        8: ["--config", args.config, "--slides-dir", "workspace/slides",
            "--audio-dir", "workspace/audio", "--manim-dir", "workspace/manim",
            "--images-dir", "workspace/images", "--sfx-dir", "workspace/sfx"],
    }
```

**New:**
```python
    stage_args = {
        1: ["--refs"] + args.refs + ["--out-dir", "workspace/transcripts"],
        2: ["--title", args.title, "--transcript-dir", "workspace/transcripts",
            "--out-dir", "workspace/scripts", "--config", args.config],
        3: ["--config", args.config, "--script-dir", "workspace/scripts",
            "--slides-dir", "workspace/slides"],
        4: ["--slides-dir", "workspace/slides", "--manim-dir", "workspace/manim"],
        5: ["--config", args.config, "--script-dir", "workspace/scripts",
            "--images-dir", "workspace/images"],
        6: ["--config", args.config, "--script-dir", "workspace/scripts",
            "--stock-dir", "workspace/stock"],
        7: ["--config", args.config, "--script-dir", "workspace/scripts",
            "--sfx-dir", "workspace/sfx"],
        8: ["--config", args.config, "--slides-dir", "workspace/slides",
            "--audio-dir", "workspace/audio"],
        9: ["--config", args.config, "--slides-dir", "workspace/slides",
            "--audio-dir", "workspace/audio", "--manim-dir", "workspace/manim",
            "--images-dir", "workspace/images", "--sfx-dir", "workspace/sfx",
            "--stock-dir", "workspace/stock"],
    }
```

- [ ] **Step 5: Update `config.example.yaml`**

Find the existing SFX block:
```yaml
freesound_api_key: "your_freesound_key_here"
sfx_count: 3            # number of SFX cues Claude selects (1-5 recommended)
```

Add the stock footage block immediately after it:
```yaml
pexels_api_key: "your_pexels_key_here"
stock_count: 3          # number of slides replaced with stock footage (1-5 recommended)
```

- [ ] **Step 6: Smoke-test the pipeline help output**

```
cd D:\01_Work\video-pipeline
python run_pipeline.py --help
```

Expected output includes:
```
--from-stage {1,2,3,4,5,6,7,8,9}
--to-stage {1,2,3,4,5,6,7,8,9}
```

- [ ] **Step 7: Run full test suite one final time**

```
pytest tests/ -v
```

Expected: all tests pass

- [ ] **Step 8: Commit**

```bash
git add run_pipeline.py config.example.yaml
git commit -m "feat: wire stage 3e into pipeline, add pexels_api_key + stock_count config"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered by |
|-----------------|------------|
| New Stage 3e between 3c and 3d | Task 2 (3e_generate_stock.py), Task 4 (run_pipeline.py stage 6) |
| Claude selects `stock_count` cues (slide_index + keyword) | Task 1 (build_stock_prompt), Task 2 (generate_cues) |
| Pexels API search + HD/SD fallback | Task 2 (search_pexels) |
| Download clips to workspace/stock/slide_NN.mp4 | Task 2 (download_clip, main) |
| Idempotent cue generation | Task 2 (stock_cues.json check) |
| Idempotent per-clip download | Task 2 (os.path.exists check) |
| Graceful skip if pexels_api_key missing | Task 2 (PEXELS_PLACEHOLDER check) |
| Error exit if anthropic_api_key missing | Task 2 (anthropic_key check) |
| substitute_stock_clip: scale to 1920x1080 | Task 3 (scale_filter) |
| substitute_stock_clip: trim if clip longer than audio | Task 3 (-t str(duration)) |
| substitute_stock_clip: pad if clip shorter than audio | Task 3 (tpad filter) |
| substitute_stock_clip: CalledProcessError handling | Task 3 (try/except, return False) |
| Assembly fallback to PNG if clip missing | Task 3 (substitute_stock_clip returns False → continue to PNG path) |
| stock_dir passed through both assemble_lang and assemble_lang_manim | Task 3 |
| Korean assembly does NOT get stock_dir | Task 3 (Korean calls unchanged) |
| run_pipeline.py: 9 stages, correct renumbering | Task 4 |
| config.example.yaml: pexels_api_key + stock_count | Task 4 |
| Unit tests: 13 covering all helpers | Task 1 |

All spec requirements covered. No placeholders found. Type consistency verified: `parse_cues` returns `list[dict]` with `slide_index` (int) and `keyword` (str) keys — used correctly in `3e_generate_stock.py` (`cue["slide_index"]`, `cue["keyword"]`) and in `substitute_stock_clip` (`f"slide_{slide_index:02d}.mp4"`).
