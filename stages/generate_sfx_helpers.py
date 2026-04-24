"""
Pure helper functions for the SFX generation stage.
No I/O, no API calls — only string manipulation and parsing.
"""

import json
import re
import urllib.parse


def build_sfx_prompt(script_text: str, sfx_count: int) -> str:
    """
    Build the user message sent to Claude to generate SFX cues.

    Args:
        script_text: Full text of the video script (script_en.md content).
        sfx_count: Number of SFX cues to request.

    Returns:
        A formatted string ready to send as a Claude user message.
    """
    return (
        f"You are a video sound designer. Read the video script below and pick exactly "
        f"{sfx_count} moments where a short sound effect would enhance the content.\n\n"
        f"For each moment, provide:\n"
        f"- slide_index: the slide number (1-based integer) where the SFX should play\n"
        f'- cue: a short Freesound.org search keyword (2-4 words, e.g. "camera shutter click")\n\n'
        f"Return ONLY a JSON array with no explanation:\n"
        f'[{{"slide_index": 2, "cue": "whoosh intro"}}, {{"slide_index": 5, "cue": "camera shutter"}}]\n\n'
        f"Script:\n{script_text}"
    )


def parse_cues(response_text: str, sfx_count: int) -> list[dict]:
    """
    Extract SFX cues from Claude's response text.

    Handles plain JSON arrays and JSON embedded in markdown code blocks.
    Skips entries that are not dicts or are missing required fields.

    Args:
        response_text: Raw text returned by Claude.
        sfx_count: Maximum number of cues to return.

    Returns:
        List of dicts with 'slide_index' (int) and 'cue' (str), up to sfx_count.

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
        cue = str(item.get("cue", "")).strip()
        if not isinstance(slide_index, int) or not cue:
            continue
        cues.append({"slide_index": slide_index, "cue": cue})

    if not cues:
        raise ValueError("No valid cues parsed from Claude response")

    return cues[:sfx_count]


def build_freesound_url(query: str, api_key: str) -> str:
    """
    Build a Freesound text search URL for the given query and API key.

    Args:
        query: Search term (e.g. "camera shutter click").
        api_key: Freesound API token.

    Returns:
        Full URL string for the Freesound search API.
    """
    encoded = urllib.parse.quote_plus(query)
    return (
        f"https://freesound.org/apiv2/search/text/"
        f"?query={encoded}&fields=id,name,previews&token={api_key}&page_size=5"
    )
