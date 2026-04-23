"""
Stage 2: Generate a 10-minute script (EN + KO) using the Claude API.

Usage:
    python stages/2_generate_script.py --title "Title" --transcript-dir workspace/transcripts

Outputs:
    workspace/scripts/script_en.md
    workspace/scripts/script_ko.md

Script format per slide:
    ## Slide N: [Section Title]
    **Headline:** [≤10 word slide headline]
    **Narration:** [full spoken narration]
"""

import argparse
import glob
import os

import anthropic
import yaml


SYSTEM_PROMPT = """You are a professional scriptwriter for educational YouTube videos.
Your scripts are engaging, clear, and structured for a narrated slideshow format."""

SCRIPT_PROMPT_TEMPLATE = """You will write a 10-minute educational video script based on the following reference transcripts, viewer comments, and title.

VIDEO TITLE: {title}

REFERENCE TRANSCRIPTS:
{transcripts}

TOP VIEWER COMMENTS (what the audience found most interesting, confusing, or valuable about this topic):
{comments}

INSTRUCTIONS:
1. Extract the 5-7 most important key ideas from the transcripts.
2. Use the viewer comments to understand what questions the audience has, what resonated with them, and what they found confusing — address these in the script.
3. Expand into a structured 10-minute script (~1,300 words at ~130 words per minute).
4. Structure:
   - Slide 1: Introduction (~1 minute, ~130 words) — hook + overview of what viewer will learn
   - Slides 2-6: Main content sections (~7 minutes total, ~140 words each)
   - Slide 7: Conclusion + Call to Action (~2 minutes, ~260 words) — key takeaways + what to do next

5. Format EACH slide EXACTLY like this (no deviation):

## Slide N: [Section Title]
**Headline:** [Slide headline in 10 words or fewer]
**Narration:** [Full narration text for this slide — complete sentences, natural speech]

6. Write engaging, conversational narration. Avoid jargon. Speak directly to the viewer.
7. Do NOT include any text outside of the slide blocks.

Write the full English script now:"""

TRANSLATE_PROMPT_TEMPLATE = """Translate the following English video script into Korean.

RULES:
- Keep the EXACT same structure and formatting (## Slide N, **Headline:**, **Narration:**)
- Translate naturally — not word-for-word. Korean should sound like a native speaker.
- Keep slide numbers and section titles translated.
- Do not add or remove slides.

ENGLISH SCRIPT:
{english_script}

Write the full Korean translation now:"""


def load_transcripts(transcript_dir: str) -> str:
    # Exclude comment files
    files = sorted(f for f in glob.glob(os.path.join(transcript_dir, "video_*.txt"))
                   if "_comments" not in f)
    if not files:
        raise FileNotFoundError(f"No transcript files found in {transcript_dir}")
    parts = []
    for i, path in enumerate(files, start=1):
        with open(path, encoding="utf-8") as f:
            content = f.read().strip()
        parts.append(f"--- Reference {i} ---\n{content}")
    return "\n\n".join(parts)


def load_comments(transcript_dir: str) -> str:
    files = sorted(glob.glob(os.path.join(transcript_dir, "video_*_comments.txt")))
    if not files:
        return "(No comments available)"
    parts = []
    for i, path in enumerate(files, start=1):
        with open(path, encoding="utf-8") as f:
            content = f.read().strip()
        parts.append(f"--- Comments from Reference {i} ---\n{content}")
    return "\n\n".join(parts)


def call_claude(client: anthropic.Anthropic, prompt: str) -> str:
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        system=SYSTEM_PROMPT,
    )
    return message.content[0].text


def main():
    parser = argparse.ArgumentParser(description="Generate video script using Claude API")
    parser.add_argument("--title", required=True, help="Video title")
    parser.add_argument("--transcript-dir", default="workspace/transcripts")
    parser.add_argument("--out-dir", default="workspace/scripts")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    api_key = cfg.get("anthropic_api_key", "")
    if not api_key or api_key.startswith("sk-ant-..."):
        raise ValueError("Set your anthropic_api_key in config.yaml")

    client = anthropic.Anthropic(api_key=api_key)
    os.makedirs(args.out_dir, exist_ok=True)

    print("[Stage 2] Loading transcripts...")
    transcripts = load_transcripts(args.transcript_dir)

    print("[Stage 2] Loading comments...")
    comments = load_comments(args.transcript_dir)
    comment_count = comments.count("\n1. ") + comments.count("\n2. ")  # rough count
    print(f"  Comments loaded ({len(comments)} chars)")

    print("[Stage 2] Generating English script (Claude API)...")
    en_prompt = SCRIPT_PROMPT_TEMPLATE.format(
        title=args.title, transcripts=transcripts, comments=comments
    )
    script_en = call_claude(client, en_prompt)
    en_path = os.path.join(args.out_dir, "script_en.md")
    with open(en_path, "w", encoding="utf-8") as f:
        f.write(f"# {args.title}\n\n{script_en}")
    print(f"  English script saved to {en_path} ({len(script_en.split())} words)")

    print("[Stage 2] Generating Korean translation (Claude API)...")
    ko_prompt = TRANSLATE_PROMPT_TEMPLATE.format(english_script=script_en)
    script_ko = call_claude(client, ko_prompt)
    ko_path = os.path.join(args.out_dir, "script_ko.md")
    with open(ko_path, "w", encoding="utf-8") as f:
        f.write(f"# {args.title}\n\n{script_ko}")
    print(f"  Korean script saved to {ko_path}")

    print("[Stage 2] Done.")


if __name__ == "__main__":
    main()
