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
