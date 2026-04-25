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
        if os.path.exists(output_path):
            os.remove(output_path)
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
