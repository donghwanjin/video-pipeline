"""
Stage 5: Assemble slide images + audio into a final video using ffmpeg.

Usage:
    python stages/5_assemble_video.py --config config.yaml

Reads:
    workspace/slides/en/slide_01.png ...
    workspace/audio/en/slide_01.mp3 ...
    (same for ko)

Outputs:
    workspace/output/video_en.mp4
    workspace/output/video_ko.mp4
"""

import argparse
import glob
import os
import subprocess
import tempfile

import yaml


def get_audio_duration(audio_path: str) -> float:
    """Use ffprobe to get audio duration in seconds."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path,
        ],
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def assemble_lang(slides_dir: str, audio_dir: str, output_path: str, lang: str):
    slide_files = sorted(glob.glob(os.path.join(slides_dir, "slide_*.png")))
    audio_files = sorted(glob.glob(os.path.join(audio_dir, "slide_*.mp3")))

    if not slide_files:
        raise FileNotFoundError(f"No slide PNGs found in {slides_dir}")
    if not audio_files:
        raise FileNotFoundError(f"No audio MP3s found in {audio_dir}")
    if len(slide_files) != len(audio_files):
        raise ValueError(
            f"Slide/audio count mismatch: {len(slide_files)} slides, {len(audio_files)} audio files"
        )

    clip_paths = []

    with tempfile.TemporaryDirectory() as tmpdir:
        for i, (slide, audio) in enumerate(zip(slide_files, audio_files), start=1):
            print(f"  [{lang}] Encoding clip {i}/{len(slide_files)}...")
            duration = get_audio_duration(audio)
            clip_path = os.path.join(tmpdir, f"clip_{i:02d}.mp4")

            # Encode one clip: hold the image for audio duration, fade in/out
            fade_dur = min(0.3, duration / 4)
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-loop", "1",
                    "-i", slide,
                    "-i", audio,
                    "-c:v", "libx264",
                    "-tune", "stillimage",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-pix_fmt", "yuv420p",
                    "-t", str(duration),
                    "-vf", f"fade=t=in:st=0:d={fade_dur},fade=t=out:st={duration - fade_dur}:d={fade_dur}",
                    "-af", f"afade=t=in:st=0:d={fade_dur},afade=t=out:st={duration - fade_dur}:d={fade_dur}",
                    "-shortest",
                    clip_path,
                ],
                check=True,
                capture_output=True,
            )
            clip_paths.append(clip_path)

        # Write concat list
        concat_list = os.path.join(tmpdir, "concat.txt")
        with open(concat_list, "w") as f:
            for path in clip_paths:
                f.write(f"file '{path}'\n")

        print(f"  [{lang}] Concatenating {len(clip_paths)} clips into {output_path}...")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_list,
                "-c", "copy",
                output_path,
            ],
            check=True,
            capture_output=True,
        )

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"  [{lang}] Done. Output: {output_path} ({size_mb:.1f} MB)")


def assemble_lang_manim(manim_dir: str, audio_dir: str, output_path: str, lang: str):
    """Assemble Manim MP4 clips + MP3 audio into final video."""
    clip_files = sorted(glob.glob(os.path.join(manim_dir, "slide_*.mp4")))
    audio_files = sorted(glob.glob(os.path.join(audio_dir, "slide_*.mp3")))

    if not clip_files:
        raise FileNotFoundError(f"No Manim MP4s found in {manim_dir}")
    if not audio_files:
        raise FileNotFoundError(f"No audio MP3s found in {audio_dir}")
    if len(clip_files) != len(audio_files):
        raise ValueError(
            f"Clip/audio count mismatch: {len(clip_files)} clips, {len(audio_files)} audio"
        )

    muxed_paths = []

    with tempfile.TemporaryDirectory() as tmpdir:
        for i, (clip, audio) in enumerate(zip(clip_files, audio_files), start=1):
            print(f"  [{lang}] Muxing clip {i}/{len(clip_files)}...")
            muxed = os.path.join(tmpdir, f"muxed_{i:02d}.mp4")
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", clip,
                    "-i", audio,
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-shortest",
                    muxed,
                ],
                check=True,
                capture_output=True,
            )
            muxed_paths.append(muxed)

        concat_list = os.path.join(tmpdir, "concat.txt")
        with open(concat_list, "w") as f:
            for path in muxed_paths:
                f.write(f"file '{path}'\n")

        print(f"  [{lang}] Concatenating {len(muxed_paths)} clips into {output_path}...")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_list,
                "-c", "copy",
                output_path,
            ],
            check=True,
            capture_output=True,
        )

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"  [{lang}] Done. Output: {output_path} ({size_mb:.1f} MB)")


def main():
    parser = argparse.ArgumentParser(description="Assemble video from slides and audio")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--slides-dir", default="workspace/slides")
    parser.add_argument("--audio-dir", default="workspace/audio")
    parser.add_argument("--manim-dir", default="workspace/manim")
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    output_dir = cfg.get("output_dir", "workspace/output")

    # English — prefer Manim clips over PNGs
    en_manim_dir = os.path.join(args.manim_dir, "en")
    if glob.glob(os.path.join(en_manim_dir, "slide_*.mp4")):
        print("[Stage 5] Assembling English video (Manim clips)...")
        assemble_lang_manim(
            en_manim_dir,
            os.path.join(args.audio_dir, "en"),
            os.path.join(output_dir, "video_en.mp4"),
            "en",
        )
    else:
        print("[Stage 5] Assembling English video (PNG slides)...")
        assemble_lang(
            os.path.join(args.slides_dir, "en"),
            os.path.join(args.audio_dir, "en"),
            os.path.join(output_dir, "video_en.mp4"),
            "en",
        )

    ko_audio_dir = os.path.join(args.audio_dir, "ko")
    if glob.glob(os.path.join(ko_audio_dir, "slide_*.mp3")):
        ko_manim_dir = os.path.join(args.manim_dir, "ko")
        if glob.glob(os.path.join(ko_manim_dir, "slide_*.mp4")):
            print("[Stage 5] Assembling Korean video (Manim clips)...")
            assemble_lang_manim(
                ko_manim_dir,
                ko_audio_dir,
                os.path.join(output_dir, "video_ko.mp4"),
                "ko",
            )
        else:
            print("[Stage 5] Assembling Korean video (PNG slides)...")
            assemble_lang(
                os.path.join(args.slides_dir, "ko"),
                ko_audio_dir,
                os.path.join(output_dir, "video_ko.mp4"),
                "ko",
            )
    else:
        print("[Stage 5] Skipping Korean video (no Korean audio found).")

    print("[Stage 5] Done.")


if __name__ == "__main__":
    main()
