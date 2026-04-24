"""
Stage 6: Generate sound effect cues using Claude, then download from Freesound.org.

Usage:
    python stages/3d_generate_sfx.py --config config.yaml

Reads:
    workspace/scripts/script_en.md

Outputs:
    workspace/sfx/sfx_cues.json
    workspace/sfx/slide_01.mp3, slide_03.mp3, ...  (one per cue)
"""

import argparse
import json
import os
import sys

import anthropic
import requests
import yaml

sys.path.insert(0, os.path.dirname(__file__))
from generate_sfx_helpers import build_sfx_prompt, parse_cues, build_freesound_url

CLAUDE_MODEL = "claude-haiku-4-5-20251001"
FREESOUND_PLACEHOLDER = "your_freesound_key_here"


def _load_config(config_path: str) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def generate_cues(script_text: str, sfx_count: int, anthropic_key: str) -> list[dict]:
    """Call Claude to generate sfx_count SFX cues from the script."""
    client = anthropic.Anthropic(api_key=anthropic_key)
    user_message = build_sfx_prompt(script_text, sfx_count)
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": user_message}],
    )
    return parse_cues(response.content[0].text, sfx_count)


def search_freesound(query: str, api_key: str) -> str | None:
    """
    Search Freesound and return the preview-hq-mp3 URL for the first result.

    Returns None if no results or the request fails.
    """
    url = build_freesound_url(query, api_key)
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  WARNING: Freesound search failed for '{query}': {exc}", file=sys.stderr)
        return None
    results = resp.json().get("results", [])
    if not results:
        return None
    previews = results[0].get("previews", {})
    preview_url = previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3")
    return preview_url


def download_sfx(url: str, output_path: str) -> bool:
    """Download SFX file from URL to output_path. Returns True on success."""
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(resp.content)
        return True
    except requests.RequestException as exc:
        print(f"  WARNING: SFX download failed: {exc}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Generate SFX cues and download audio")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--script-dir", default="workspace/scripts")
    parser.add_argument("--sfx-dir", default="workspace/sfx")
    args = parser.parse_args()

    cfg = _load_config(args.config)

    freesound_key = cfg.get("freesound_api_key", FREESOUND_PLACEHOLDER)
    if not freesound_key or freesound_key == FREESOUND_PLACEHOLDER:
        print("[Stage 6] WARNING: freesound_api_key not set. Skipping SFX generation.")
        return

    anthropic_key = cfg.get("anthropic_api_key", "")
    if not anthropic_key or anthropic_key.startswith("sk-ant-..."):
        print("[Stage 6] ERROR: anthropic_api_key not set in config.", file=sys.stderr)
        sys.exit(1)

    sfx_count = int(cfg.get("sfx_count", 3))

    script_path = os.path.join(args.script_dir, "script_en.md")
    if not os.path.exists(script_path):
        print(f"[Stage 6] ERROR: script not found: {script_path}", file=sys.stderr)
        sys.exit(1)

    with open(script_path, encoding="utf-8") as f:
        script_text = f.read()

    os.makedirs(args.sfx_dir, exist_ok=True)

    # Step 1: Generate cues (or load existing — idempotent)
    cues_path = os.path.join(args.sfx_dir, "sfx_cues.json")
    if os.path.exists(cues_path):
        print(f"[Stage 6] Loading existing cues from {cues_path}")
        with open(cues_path, encoding="utf-8") as f:
            cues = json.load(f)
    else:
        print(f"[Stage 6] Generating {sfx_count} SFX cues via Claude...")
        cues = generate_cues(script_text, sfx_count, anthropic_key)
        with open(cues_path, "w", encoding="utf-8") as f:
            json.dump(cues, f, indent=2, ensure_ascii=False)
        print(f"[Stage 6] Cues saved to {cues_path}")

    # Step 2: Download SFX files (skip already-downloaded — idempotent)
    downloaded = 0
    for cue in cues:
        slide_index = cue["slide_index"]
        query = cue["cue"]
        out_path = os.path.join(args.sfx_dir, f"slide_{slide_index:02d}.mp3")

        if os.path.exists(out_path):
            print(f"[Stage 6] Skipping slide {slide_index} SFX (already exists)")
            downloaded += 1
            continue

        print(f"[Stage 6] Searching Freesound for '{query}' (slide {slide_index})...")
        preview_url = search_freesound(query, freesound_key)
        if not preview_url:
            print(f"  WARNING: No Freesound results for '{query}'. Skipping.", file=sys.stderr)
            continue

        if download_sfx(preview_url, out_path):
            size_kb = os.path.getsize(out_path) / 1024
            print(f"[Stage 6]   Saved {out_path} ({size_kb:.0f} KB)")
            downloaded += 1

    print(f"[Stage 6] Done. {downloaded}/{len(cues)} SFX files available in {args.sfx_dir}")


if __name__ == "__main__":
    main()
