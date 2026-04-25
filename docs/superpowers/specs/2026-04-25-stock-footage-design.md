# Stock Footage Design

**Date:** 2026-04-25
**Status:** Approved

---

## Goal

Automatically replace a configurable number of slides with relevant stock video clips sourced from the Pexels API. Claude reads the script and selects the best N moments (by slide index + search keyword); the pipeline downloads matching clips and substitutes them during final video assembly. Narration audio is preserved — each clip plays for the same duration as its corresponding slide audio.

---

## Architecture

Stock footage is handled by a new Stage 3e inserted between image generation (3c) and SFX (3d). Assembly (Stage 5) is modified to substitute stock clips for tagged slides.

```
Stage 1  fetch_transcripts
Stage 2  generate_script
Stage 3  generate_slides
Stage 3b generate_manim
Stage 3c generate_images
Stage 3e generate_stock       ← NEW
Stage 3d generate_sfx
Stage 4  generate_audio
Stage 5  assemble_video       ← MODIFIED
```

### Stage 3e flow

1. Read `workspace/scripts/script_en.md`
2. Call Claude (`claude-haiku-4-5-20251001`) → returns exactly `stock_count` cues as JSON:
   ```json
   [{"slide_index": 2, "keyword": "ancient roman forum"}, ...]
   ```
3. Write `workspace/stock/stock_cues.json` — idempotent (skip if file already exists)
4. For each cue: search Pexels with keyword, download best matching clip as `workspace/stock/slide_NN.mp4` — idempotent per file
5. Graceful skip if `pexels_api_key` is missing or set to placeholder value

### Assembly change (Stage 5)

During base video construction, before encoding a slide:
- Check if the slide index appears in `stock_cues.json` and its `.mp4` file exists
- If yes: use the stock clip, trimmed or padded to match the narration audio duration for that slide
- If no (or clip missing): fall back to normal PNG+audio encoding

Stock substitution applies to English video only (same scoping as SFX).

---

## File Structure

| File | Status | Responsibility |
|------|--------|----------------|
| `stages/generate_stock_helpers.py` | NEW | Pure helper functions: `build_stock_prompt()`, `parse_cues()`, `build_pexels_url()` |
| `stages/3e_generate_stock.py` | NEW | Main stage: Claude cue generation + Pexels download |
| `tests/test_generate_stock_helpers.py` | NEW | Unit tests for all helper functions |
| `stages/5_assemble_video.py` | MODIFIED | Substitute stock clip for tagged slides during assembly |
| `run_pipeline.py` | MODIFIED | Insert stage 3e, add `stock_count` to stage args |
| `config.example.yaml` | MODIFIED | Add `pexels_api_key`, `stock_count` |

### Workspace output

```
workspace/stock/
  stock_cues.json
  slide_03.mp4
  slide_07.mp4
```

---

## Configuration

```yaml
pexels_api_key: "your_pexels_key_here"
stock_count: 3    # number of slides Claude replaces with stock footage (1-5 recommended)
```

---

## Helper Functions (`generate_stock_helpers.py`)

### `build_stock_prompt(script_text: str, stock_count: int) -> str`

Constructs a Claude prompt asking it to read the script and return exactly `stock_count` cues as a JSON array. Each cue must have `slide_index` (0-based integer) and `keyword` (concise search phrase for Pexels). Prompt instructs Claude to pick visually rich moments best served by real-world footage.

### `parse_cues(response: str, stock_count: int) -> list[dict]`

Extracts cues from Claude's response. Handles both plain JSON and markdown-fenced blocks (` ```json ... ``` `). Wraps `json.loads()` in `try/except JSONDecodeError`, re-raising as `ValueError`. Validates each entry has `slide_index` (int) and `keyword` (non-empty string); skips invalid entries with a warning. Raises `ValueError` if result is empty. Truncates to `stock_count` if Claude returns extras.

### `build_pexels_url(keyword: str) -> str`

Returns the Pexels video search URL with the keyword query-encoded. Example:
```
https://api.pexels.com/videos/search?query=ancient+roman+forum&per_page=5&orientation=landscape
```

---

## Stage 3e (`3e_generate_stock.py`)

**Constants:**
- `CLAUDE_MODEL = "claude-haiku-4-5-20251001"`
- `PEXELS_PLACEHOLDER = "your_pexels_key_here"`

**Functions:**

### `generate_cues(script_text, stock_count, anthropic_key) -> list[dict]`

Calls Claude with the prompt from `build_stock_prompt()`. Returns parsed cues.

### `search_pexels(keyword, api_key) -> str | None`

Calls Pexels video search API with `Authorization: {api_key}` header. Returns the HD video file URL (`hd` quality) from the first result, falling back to `sd` if `hd` is absent. Returns `None` if no results.

### `download_clip(url, output_path) -> bool`

Downloads the MP4 file to disk via `requests`. Returns `True` on success, `False` on failure.

### `main()`

1. Load config, read script
2. If `pexels_api_key` missing or placeholder: print skip message, exit 0
3. If `anthropic_api_key` missing: print error, exit 1
4. If `stock_cues.json` exists: load and skip cue generation (idempotent)
5. Otherwise: generate cues, write `stock_cues.json`
6. For each cue: skip if clip already exists, else search Pexels + download

---

## Assembly Integration (`5_assemble_video.py`)

### New function: `substitute_stock_clip(slide_index, stock_dir, audio_path) -> str | None`

Returns path to a temp MP4 of the stock clip trimmed/padded to match `audio_path` duration, or `None` if no clip available for this index. Uses ffmpeg:
- Trim: `-t {duration}`
- Pad (if clip shorter than audio): `tpad=stop_mode=clone:stop_duration={gap}` filter

### Modified: `build_base_video()`

Before encoding each slide, call `substitute_stock_clip()`. If it returns a path, use that clip (mux with audio) instead of the normal PNG encoding.

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| `pexels_api_key` missing or placeholder | Stage 3e exits cleanly (exit 0), assembly uses PNG slides |
| Pexels returns no results for keyword | Log warning, skip cue, continue |
| Download fails | Log warning, skip cue; assembly falls back to PNG |
| Clip shorter than slide audio | ffmpeg `tpad` to extend |
| Clip longer than slide audio | ffmpeg `-t` to trim |
| `stock_cues.json` present but clip missing | Assembly falls back to PNG for that slide |
| Slide index out of range | Log warning, skip cue |
| Claude returns malformed JSON | Raise `ValueError` with message |
| Claude returns non-list JSON | Raise `ValueError("Expected JSON array")` |

---

## Testing

Unit tests cover `generate_stock_helpers.py` only (pure functions, no I/O):

### `TestBuildStockPrompt`
- Returns a string
- Contains `stock_count` as a number
- Contains script excerpt
- Specifies JSON output
- Specifies `slide_index` and `keyword` fields

### `TestParseCues`
- Parses plain JSON array
- Extracts JSON from markdown-fenced block
- Truncates to `stock_count`
- Raises on empty array
- Raises on non-list JSON
- Raises on malformed JSON (`JSONDecodeError` → `ValueError`)
- Strips whitespace from keyword
- Skips entries missing `slide_index` or `keyword`
- Raises when all entries are invalid

### `TestBuildPexelsUrl`
- Encodes spaces as `+`
- Includes keyword
- Targets `api.pexels.com`
