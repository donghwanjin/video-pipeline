"""
Stage 5: Generate AI images using Claude (prompts) + Flux via Replicate (images).

Usage:
    python stages/3c_generate_images.py --config config.yaml --script-dir workspace/scripts --images-dir workspace/images

Reads:
    workspace/scripts/script_en.md

Outputs:
    workspace/images/en/prompts.json
    workspace/images/en/image_01.png … image_N.png
"""

import argparse
import json
import os
import sys
import urllib.request

import anthropic
import yaml

# stages/ is the parent directory of this file
sys.path.insert(0, os.path.dirname(__file__))
from generate_images_helpers import build_prompt_request, parse_prompts

FLUX_MODEL = "black-forest-labs/flux-schnell"
IMAGE_WIDTH = 1920
IMAGE_HEIGHT = 1080
CLAUDE_MODEL = "claude-haiku-4-5-20251001"


def _load_config(config_path: str) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def generate_prompts(script_text: str, image_count: int, anthropic_key: str) -> list[str]:
    """Call Claude to generate image_count cinematic prompts from the script."""
    client = anthropic.Anthropic(api_key=anthropic_key)
    user_message = build_prompt_request(script_text, image_count)
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": user_message}],
    )
    return parse_prompts(response.content[0].text, image_count)


def generate_image(prompt: str, output_path: str, replicate_api_key: str) -> bool:
    """
    Generate one image via Replicate Flux and save to output_path.
    Returns True on success, False on failure (logs warning).
    """
    import replicate

    try:
        output = replicate.run(
            FLUX_MODEL,
            input={
                "prompt": prompt,
                "width": IMAGE_WIDTH,
                "height": IMAGE_HEIGHT,
                "num_outputs": 1,
            },
        )
        # output is a list of FileOutput objects with a url attribute
        image_url = str(output[0])
        urllib.request.urlretrieve(image_url, output_path)
        return True
    except Exception as exc:
        print(f"  WARNING: image generation failed: {exc}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Generate AI images for video outro")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--script-dir", default="workspace/scripts")
    parser.add_argument("--images-dir", default="workspace/images")
    args = parser.parse_args()

    cfg = _load_config(args.config)

    replicate_key = cfg.get("replicate_api_key", "r8_...")
    if not replicate_key or replicate_key == "r8_...":
        print("[Stage 5] WARNING: replicate_api_key not set. Skipping image generation.")
        return

    anthropic_key = cfg.get("anthropic_api_key", "")
    if not anthropic_key or anthropic_key.startswith("sk-ant-..."):
        print("[Stage 5] ERROR: anthropic_api_key not set in config.", file=sys.stderr)
        sys.exit(1)
    image_count = int(cfg.get("image_count", 6))

    script_path = os.path.join(args.script_dir, "script_en.md")
    if not os.path.exists(script_path):
        print(f"[Stage 5] ERROR: script not found: {script_path}", file=sys.stderr)
        sys.exit(1)

    with open(script_path, encoding="utf-8") as f:
        script_text = f.read()

    out_dir = os.path.join(args.images_dir, "en")
    os.makedirs(out_dir, exist_ok=True)

    # Step 1: Generate prompts (or load existing)
    prompts_path = os.path.join(out_dir, "prompts.json")
    if os.path.exists(prompts_path):
        print(f"[Stage 5] Loading existing prompts from {prompts_path}")
        with open(prompts_path, encoding="utf-8") as f:
            prompts = json.load(f)
    else:
        print(f"[Stage 5] Generating {image_count} image prompts via Claude...")
        prompts = generate_prompts(script_text, image_count, anthropic_key)
        with open(prompts_path, "w", encoding="utf-8") as f:
            json.dump(prompts, f, indent=2, ensure_ascii=False)
        print(f"[Stage 5] Prompts saved to {prompts_path}")

    # Step 2: Generate images (skip already-generated)
    os.environ["REPLICATE_API_TOKEN"] = replicate_key
    generated = 0
    for i, prompt in enumerate(prompts, start=1):
        img_path = os.path.join(out_dir, f"image_{i:02d}.png")
        if os.path.exists(img_path):
            print(f"[Stage 5] Skipping image {i} (already exists)")
            generated += 1
            continue
        print(f"[Stage 5] Generating image {i}/{len(prompts)}...")
        if generate_image(prompt, img_path, replicate_key):
            size_kb = os.path.getsize(img_path) / 1024
            print(f"[Stage 5]   Saved {img_path} ({size_kb:.0f} KB)")
            generated += 1

    print(f"[Stage 5] Done. {generated}/{len(prompts)} images available in {out_dir}")


if __name__ == "__main__":
    main()
