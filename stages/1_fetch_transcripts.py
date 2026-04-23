"""
Stage 1: Fetch YouTube transcripts and top 100 comments.

Usage:
    python stages/1_fetch_transcripts.py --refs URL1 URL2 ...

Outputs:
    workspace/transcripts/video_1.txt
    workspace/transcripts/video_1_comments.txt
    workspace/transcripts/video_2.txt
    workspace/transcripts/video_2_comments.txt
    ...
"""

import argparse
import os
import re
import sys

from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
from youtube_comment_downloader import YoutubeCommentDownloader, SORT_BY_POPULAR


def extract_video_id(url: str) -> str:
    patterns = [
        r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:embed/)([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"Could not extract video ID from URL: {url}")


def fetch_transcript(video_id: str) -> str:
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        # Prefer manual captions, fall back to auto-generated
        try:
            transcript = transcript_list.find_manually_created_transcript(["en", "ko"])
        except Exception:
            transcript = transcript_list.find_generated_transcript(["en", "ko"])
        fetched = transcript.fetch()
        # Support both old dict-style and new object-style entries
        def get_text(entry):
            return entry.text if hasattr(entry, "text") else entry["text"]
        return " ".join(get_text(e) for e in fetched)
    except (NoTranscriptFound, TranscriptsDisabled) as e:
        print(f"  WARNING: No transcript available for {video_id}: {e}", file=sys.stderr)
        return ""


def fetch_comments(url: str, max_comments: int = 100) -> list[str]:
    """Fetch top comments from a YouTube video URL."""
    try:
        downloader = YoutubeCommentDownloader()
        comments = []
        for comment in downloader.get_comments_from_url(url, sort_by=SORT_BY_POPULAR):
            text = comment.get("text", "").strip()
            if text:
                comments.append(text)
            if len(comments) >= max_comments:
                break
        return comments
    except Exception as e:
        print(f"  WARNING: Could not fetch comments: {e}", file=sys.stderr)
        return []


def main():
    parser = argparse.ArgumentParser(description="Fetch YouTube transcripts and comments")
    parser.add_argument("--refs", nargs="+", required=True, help="YouTube URLs")
    parser.add_argument("--out-dir", default="workspace/transcripts")
    parser.add_argument("--max-comments", type=int, default=100)
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    fetched = 0

    for i, url in enumerate(args.refs, start=1):
        print(f"[Stage 1] Processing video {i}/{len(args.refs)}: {url}")
        try:
            video_id = extract_video_id(url)

            # Transcript
            print(f"  Fetching transcript...")
            text = fetch_transcript(video_id)
            if text:
                out_path = os.path.join(args.out_dir, f"video_{i}.txt")
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(text)
                print(f"  Transcript: {len(text)} chars -> {out_path}")
                fetched += 1
            else:
                print(f"  No transcript available, skipping.")

            # Comments
            print(f"  Fetching top {args.max_comments} comments...")
            comments = fetch_comments(url, max_comments=args.max_comments)
            if comments:
                comments_path = os.path.join(args.out_dir, f"video_{i}_comments.txt")
                with open(comments_path, "w", encoding="utf-8") as f:
                    for j, c in enumerate(comments, start=1):
                        f.write(f"{j}. {c}\n\n")
                print(f"  Comments: {len(comments)} saved -> {comments_path}")
            else:
                print(f"  No comments retrieved.")

        except ValueError as e:
            print(f"  ERROR: {e}", file=sys.stderr)

    print(f"[Stage 1] Done. {fetched}/{len(args.refs)} transcripts fetched.")
    if fetched == 0:
        print("ERROR: No transcripts fetched. Cannot continue.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
