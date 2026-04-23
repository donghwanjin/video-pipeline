"""
Pure helper functions for the AI image generation stage.
No I/O, no API calls — only string manipulation and parsing.
"""

import json
import re


def build_prompt_request(script_text: str, image_count: int) -> str:
    """
    Build the user message sent to Claude to generate image prompts.

    Args:
        script_text: Full text of the video script (script_en.md content).
        image_count: Number of prompts to request.

    Returns:
        A formatted string ready to send as a Claude user message.
    """
    return (
        f"You are a cinematic art director. Read the video script below and produce "
        f"exactly {image_count} image prompts as a JSON array of strings.\n\n"
        f"Rules for each prompt:\n"
        f"- One prompt per key visual moment or topic in the script\n"
        f"- Visually evocative and cinematic — describe the scene, lighting, mood\n"
        f"- No text, no UI elements, no labels anywhere in the image\n"
        f"- Dark, dramatic aesthetic (deep shadows, moody lighting)\n"
        f"- Suitable for a 1920x1080 widescreen landscape image\n"
        f"- Do NOT reference any characters by name if they are fictional\n\n"
        f"Return ONLY a JSON array of {image_count} strings. No explanation.\n\n"
        f"Script:\n{script_text}"
    )


def parse_prompts(response_text: str, image_count: int) -> list[str]:
    """
    Extract image prompts from Claude's response text.

    Handles plain JSON arrays and JSON embedded in markdown code blocks.

    Args:
        response_text: Raw text returned by Claude.
        image_count: Maximum number of prompts to return.

    Returns:
        List of prompt strings (up to image_count).

    Raises:
        ValueError: If no prompts could be parsed.
    """
    text = response_text.strip()

    # Strip markdown code fences if present
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()

    prompts: list[str] = json.loads(text)
    if not isinstance(prompts, list):
        raise ValueError(f"Expected JSON array from Claude, got {type(prompts).__name__}")

    if not prompts:
        raise ValueError("No prompts parsed from Claude response")

    # Strip whitespace and filter out empty strings
    prompts = [str(p).strip() for p in prompts]
    prompts = [p for p in prompts if p]
    if not prompts:
        raise ValueError("No prompts parsed from Claude response")
    return prompts[:image_count]
