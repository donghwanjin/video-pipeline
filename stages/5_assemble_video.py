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
import json
import os
import shutil
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


def append_outro_gallery(video_path: str, images_dir: str) -> None:
    """
    Append a silent Ken Burns outro gallery to video_path.

    Each image is shown for 10 / image_count seconds with a slow zoom-in.
    The gallery is concatenated directly onto the existing video.
    Requires at least 2 images; skips silently if fewer are found.

    Args:
        video_path: Path to the main video file to extend (modified in place).
        images_dir: Directory containing image_01.png … image_N.png
    """
    image_files = sorted(glob.glob(os.path.join(images_dir, "image_*.png")))
    if len(image_files) < 2:
        print(f"  [outro] Fewer than 2 images found in {images_dir}. Skipping outro gallery.")
        return

    image_count = len(image_files)
    duration_each = 10.0 / image_count  # total gallery ~10 s

    print(f"  [outro] Building outro gallery: {image_count} images × {duration_each:.2f}s each")

    with tempfile.TemporaryDirectory() as tmpdir:
        gallery_clips = []

        for i, img_path in enumerate(image_files, start=1):
            clip_path = os.path.join(tmpdir, f"gallery_{i:02d}.mp4")
            # Ken Burns: slow zoom from 1.0x to 1.05x over duration_each seconds
            fps = 25
            total_frames = int(fps * duration_each)
            zoom_increment = 0.05 / total_frames
            zoom_expr = f"min(zoom+{zoom_increment:.6f},1.05)"
            # x/y keep the image centred as zoom grows
            zoompan_filter = (
                f"zoompan=z='{zoom_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                f":d={total_frames}:s=1920x1080:fps={fps}"
            )
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-loop", "1",
                    "-i", img_path,
                    "-vf", zoompan_filter,
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-t", f"{duration_each:.2f}",
                    "-an",  # silent — no audio track
                    clip_path,
                ],
                check=True,
                capture_output=True,
            )
            gallery_clips.append(clip_path)

        # Concatenate gallery clips into one outro file
        outro_path = os.path.join(tmpdir, "outro.mp4")
        concat_list = os.path.join(tmpdir, "gallery_concat.txt")
        with open(concat_list, "w") as f:
            for path in gallery_clips:
                f.write(f"file '{path.replace(chr(92), '/')}'\n")
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_list,
                "-c", "copy",
                outro_path,
            ],
            check=True,
            capture_output=True,
        )

        # The main video has audio; outro is silent — add silent audio track to outro
        outro_with_audio = os.path.join(tmpdir, "outro_audio.mp4")
        duration_outro = duration_each * image_count
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", outro_path,
                "-f", "lavfi",
                "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
                "-map", "0:v",
                "-map", "1:a",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-t", f"{duration_outro:.2f}",
                outro_with_audio,
            ],
            check=True,
            capture_output=True,
        )

        # Concatenate main video + outro
        extended_path = os.path.join(tmpdir, "extended.mp4")
        final_concat = os.path.join(tmpdir, "final_concat.txt")
        with open(final_concat, "w") as f:
            f.write(f"file '{os.path.abspath(video_path).replace(chr(92), '/')}'\n")
            f.write(f"file '{outro_with_audio.replace(chr(92), '/')}'\n")
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", final_concat,
                "-c", "copy",
                extended_path,
            ],
            check=True,
            capture_output=True,
        )

        # Replace the original video with the extended one
        shutil.move(extended_path, video_path)

    size_mb = os.path.getsize(video_path) / (1024 * 1024)
    print(f"  [outro] Extended video saved: {video_path} ({size_mb:.1f} MB)")


def mix_sfx_into_video(video_path: str, sfx_dir: str, audio_dir: str) -> None:
    """
    Mix SFX files into the video at their cued slide timestamps.

    Reads sfx_cues.json from sfx_dir to determine which slides get SFX.
    Computes each slide's start time from narration audio durations.
    Layers SFX at -20 dBFS using ffmpeg adelay + amix. Modifies video_path in place.

    Args:
        video_path: Path to the video file to modify in place.
        sfx_dir: Directory containing sfx_cues.json and slide_N.mp3 files.
        audio_dir: Directory containing narration slide_*.mp3 files (used for timing).
    """
    cues_path = os.path.join(sfx_dir, "sfx_cues.json")
    if not os.path.exists(cues_path):
        return

    with open(cues_path, encoding="utf-8") as f:
        cues = json.load(f)

    # Build slide start-time map from narration audio durations
    audio_files = sorted(glob.glob(os.path.join(audio_dir, "slide_*.mp3")))
    slide_timestamps: dict[int, float] = {}
    cumulative = 0.0
    for i, audio_file in enumerate(audio_files, start=1):
        slide_timestamps[i] = cumulative
        try:
            cumulative += get_audio_duration(audio_file)
        except (ValueError, Exception) as exc:
            print(f"  [sfx] WARNING: could not read duration of {audio_file}: {exc}")
            cumulative += 0.0

    # Collect valid cues: slide must exist in timestamps and SFX file must be downloaded
    valid_cues: list[tuple[float, str]] = []
    for cue in cues:
        slide_index = cue["slide_index"]
        sfx_path = os.path.join(sfx_dir, f"slide_{slide_index:02d}.mp3")
        if slide_index not in slide_timestamps:
            print(f"  [sfx] WARNING: slide {slide_index} not in audio files. Skipping cue.")
            continue
        if not os.path.exists(sfx_path):
            print(f"  [sfx] WARNING: {sfx_path} not found. Skipping cue.")
            continue
        valid_cues.append((slide_timestamps[slide_index], sfx_path))

    if not valid_cues:
        print("  [sfx] No valid SFX cues found. Skipping SFX mixing.")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = ["ffmpeg", "-y", "-i", video_path]
        for _, sfx_path in valid_cues:
            cmd += ["-i", sfx_path]

        filter_parts = []
        for i, (start_time, _) in enumerate(valid_cues):
            delay_ms = int(start_time * 1000)
            filter_parts.append(
                f"[{i + 1}:a]volume=0.1,adelay={delay_ms}|{delay_ms}[sfx{i}]"
            )

        sfx_labels = "".join(f"[sfx{i}]" for i in range(len(valid_cues)))
        n_inputs = len(valid_cues) + 1
        filter_parts.append(
            f"[0:a]{sfx_labels}amix=inputs={n_inputs}:duration=first:normalize=0[aout]"
        )

        out_path = os.path.join(tmpdir, "with_sfx.mp4")
        cmd += [
            "-filter_complex", ";".join(filter_parts),
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            out_path,
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"[sfx] ffmpeg SFX mix failed: {exc.stderr.decode(errors='replace')}"
            ) from exc
        shutil.move(out_path, video_path)

    print(f"  [sfx] Mixed {len(valid_cues)} SFX into {video_path}")


def main():
    parser = argparse.ArgumentParser(description="Assemble video from slides and audio")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--slides-dir", default="workspace/slides")
    parser.add_argument("--audio-dir", default="workspace/audio")
    parser.add_argument("--manim-dir", default="workspace/manim")
    parser.add_argument("--images-dir", default="workspace/images")
    parser.add_argument("--sfx-dir", default="workspace/sfx")
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

    # Mix SFX into English video only (Korean SFX not supported)
    if os.path.exists(os.path.join(args.sfx_dir, "sfx_cues.json")):
        print("[Stage 5] Mixing SFX into English video...")
        mix_sfx_into_video(
            os.path.join(output_dir, "video_en.mp4"),
            args.sfx_dir,
            os.path.join(args.audio_dir, "en"),
        )

    # Append AI image outro gallery if images exist
    en_images_dir = os.path.join(args.images_dir, "en")
    if glob.glob(os.path.join(en_images_dir, "image_*.png")):
        print("[Stage 5] Appending AI image outro gallery to English video...")
        append_outro_gallery(
            os.path.join(output_dir, "video_en.mp4"),
            en_images_dir,
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
