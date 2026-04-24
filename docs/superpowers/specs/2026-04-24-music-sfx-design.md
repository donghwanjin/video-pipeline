# Music & SFX Design Spec

## Goal

Add Claude-generated sound effect cues to the video pipeline. Claude reads the English script and selects N moments where SFX enhance the content. Freesound.org provides the audio files. The final video has SFX layered onto the narration audio at the correct timestamps.

## Scope

- Sound effects only — no background music
- English video only (same pattern as AI images)
- SFX are mixed additively over narration; narration is never replaced or ducked

---

## Architecture

The feature adds one new pipeline stage and modifies the assembly stage:

```
Stage 1: fetch_transcripts
Stage 2: generate_script
Stage 3: generate_slides
Stage 4: generate_manim       (3b_generate_manim.py)
Stage 5: generate_images      (3c_generate_images.py)
Stage 6: generate_sfx         (3d_generate_sfx.py)  ← NEW
Stage 7: generate_audio       (4_generate_audio.py)
Stage 8: assemble_video       (5_assemble_video.py) ← MODIFIED
```

Stage 6 only depends on the script (stage 2 output). It can run any time after stage 2.

---

## Stage 6: generate_sfx

### Inputs
- `workspace/script/script_en.md` — full English narration script
- `config.yaml` — `anthropic_api_key`, `freesound_api_key`, `sfx_count` (default: 3)

### Process

1. **Read script** from `workspace/script/script_en.md`
2. **Check idempotency** — if `workspace/sfx/sfx_cues.json` already exists, skip Claude call
3. **Call Claude** (`claude-haiku-4-5-20251001`) to generate SFX cues
   - Output format: JSON array of `{"slide_index": int, "cue": "search keyword string"}`
   - Example: `[{"slide_index": 1, "cue": "whoosh intro"}, {"slide_index": 4, "cue": "camera shutter"}]`
   - `slide_index` is 1-based, matching `slide_01.mp3` convention
4. **Save cues** to `workspace/sfx/sfx_cues.json`
5. **For each cue**, search Freesound.org API:
   - `GET https://freesound.org/apiv2/search/text/?query=<cue>&fields=id,name,previews&token=<key>&page_size=5`
   - Select the first result
   - Download `previews.preview-hq-mp3` URL to `workspace/sfx/slide_<N>.mp3`
   - Skip if file already exists (idempotency)
   - If no results or download fails, log a warning and continue

### Outputs
- `workspace/sfx/sfx_cues.json`
- `workspace/sfx/slide_01.mp3`, `slide_04.mp3`, etc. (one per cue)

### Graceful degradation
- If `freesound_api_key` is missing or equals the placeholder string `"your_freesound_key_here"`, print a warning and exit 0 (skip stage)
- If `anthropic_api_key` is missing, exit with error

---

## Stage 8 modification: assemble_video

### New function: `mix_sfx_into_video(video_path, sfx_dir, audio_dir)`

Called after the main English video is assembled, before the outro gallery is appended.

**Process:**
1. Read `sfx_dir/sfx_cues.json` — if missing, return immediately (no-op)
2. For each slide, get its audio duration using `ffprobe` to build a timestamp map:
   - `slide_timestamps[slide_index] = sum of durations of slides 1..(slide_index-1)`
3. For each cue in `sfx_cues.json`:
   - Check `sfx_dir/slide_<N>.mp3` exists — skip if missing
   - Compute `delay_ms = slide_timestamps[slide_index] * 1000`
4. Build an ffmpeg command that:
   - Takes the main video as input
   - Takes each SFX mp3 as additional inputs
   - Normalizes each SFX to -20 dBFS with `volume=-20dB`
   - Applies `adelay=<delay_ms>|<delay_ms>` to position each SFX
   - Mixes all streams with `amix=inputs=<N+1>:duration=first:normalize=0`
   - Copies video stream, re-encodes audio as AAC 192k
   - Outputs to a temp file, then replaces the original video

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `stages/generate_sfx_helpers.py` | Create | Pure functions: build Claude prompt, parse Claude JSON response, build Freesound search URL |
| `stages/3d_generate_sfx.py` | Create | Stage orchestration: read script, call Claude, search Freesound, download files |
| `tests/test_generate_sfx_helpers.py` | Create | Unit tests for all helper functions |
| `stages/5_assemble_video.py` | Modify | Add `mix_sfx_into_video()`, call it in `main()` after English video assembly |
| `run_pipeline.py` | Modify | Insert stage 6, renumber audio → 7, assemble → 8, update CLI choices |
| `config.example.yaml` | Modify | Add `freesound_api_key` and `sfx_count: 3` |
| `requirements.txt` | Modify | Add `requests>=2.31.0` |

---

## Config

```yaml
freesound_api_key: "your_freesound_key_here"
sfx_count: 3   # number of SFX cues Claude selects (1-5 recommended)
```

---

## Error Handling & Edge Cases

| Scenario | Behaviour |
|----------|-----------|
| `freesound_api_key` missing or placeholder | Warn + exit 0 (stage skipped) |
| `anthropic_api_key` missing | Exit with error |
| Freesound returns no results for a cue | Log warning, skip that cue, continue |
| Freesound download fails | Log warning, skip that cue, continue |
| `sfx_cues.json` missing at assembly time | `mix_sfx_into_video` returns immediately, video unchanged |
| SFX file missing at assembly time | Skip that cue, mix remaining |
| `sfx_cues.json` already exists | Skip Claude call (idempotent) |
| Individual `slide_N.mp3` already exists | Skip download (idempotent) |
| SFX volume too loud | Normalized to -20 dBFS before mixing |

---

## Testing

- Unit tests for `generate_sfx_helpers.py`:
  - `build_prompt_request(script_text, sfx_count)` returns string containing script and count
  - `parse_cues(response_text, sfx_count)` parses plain JSON and markdown-fenced JSON
  - `parse_cues` raises `ValueError` on empty array
  - `parse_cues` raises `ValueError` on non-list JSON
  - `parse_cues` truncates to `sfx_count` if Claude returns more
  - `build_freesound_url(query, api_key)` returns correctly encoded URL

- Integration behaviour (not unit tested):
  - Stage 6 skips gracefully with missing API key
  - Assembly skips SFX mixing when no `sfx_cues.json`

---

## Workspace Layout

```
workspace/
  script/
    script_en.md          (input)
  sfx/
    sfx_cues.json         (Claude output, saved for inspection)
    slide_01.mp3          (Freesound download)
    slide_04.mp3
  output/
    video_en.mp4          (modified in-place with SFX mixed in)
```
