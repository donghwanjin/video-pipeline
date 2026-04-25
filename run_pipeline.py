"""
Video Creation Pipeline — Main Orchestrator

Usage from Claude Code chat:
    python run_pipeline.py --title "Your Video Title" --refs URL1 URL2

Or run individual stages:
    python run_pipeline.py --title "..." --refs URL1 --from-stage 3

Stages:
    1  fetch_transcripts
    2  generate_script
    3  generate_slides
    4  generate_manim     (cinematic Manim animations)
    5  generate_images    (AI images via Flux for outro gallery)
    6  generate_stock     (Claude stock cues + Pexels download)
    7  generate_sfx       (Claude SFX cues + Freesound download)
    8  generate_audio
    9  assemble_video     (stock substitution + SFX mix + AI image outro)
"""

import argparse
import subprocess
import sys
import os

PYTHON = sys.executable

STAGES = [
    (1, "Fetch Transcripts", "stages/1_fetch_transcripts.py"),
    (2, "Generate Script",   "stages/2_generate_script.py"),
    (3, "Generate Slides",   "stages/3_generate_slides.py"),
    (4, "Generate Manim",    "stages/3b_generate_manim.py"),
    (5, "Generate Images",   "stages/3c_generate_images.py"),
    (6, "Generate Stock",    "stages/3e_generate_stock.py"),
    (7, "Generate SFX",      "stages/3d_generate_sfx.py"),
    (8, "Generate Audio",    "stages/4_generate_audio.py"),
    (9, "Assemble Video",    "stages/5_assemble_video.py"),
]


def run_stage(script: str, extra_args: list[str], stage_num: int, stage_name: str):
    print(f"\n{'='*60}")
    print(f"  STAGE {stage_num}: {stage_name.upper()}")
    print(f"{'='*60}")
    cmd = [PYTHON, script] + extra_args
    result = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))
    if result.returncode != 0:
        print(f"\nERROR: Stage {stage_num} ({stage_name}) failed. Stopping pipeline.", file=sys.stderr)
        sys.exit(result.returncode)


def main():
    parser = argparse.ArgumentParser(
        description="Automated video creation pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--title", required=True, help="Video title")
    parser.add_argument("--refs", nargs="+", required=True, help="YouTube reference URLs")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument(
        "--from-stage", type=int, default=1, choices=[1, 2, 3, 4, 5, 6, 7, 8, 9],
        help="Resume from this stage (skip earlier stages)"
    )
    parser.add_argument(
        "--to-stage", type=int, default=9, choices=[1, 2, 3, 4, 5, 6, 7, 8, 9],
        help="Stop after this stage"
    )
    args = parser.parse_args()

    # Change to pipeline directory so relative paths work
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    print(f"\nVideo Pipeline")
    print(f"  Title : {args.title}")
    print(f"  Refs  : {', '.join(args.refs)}")
    print(f"  Stages: {args.from_stage} -> {args.to_stage}")

    # Build per-stage argument lists
    stage_args = {
        1: ["--refs"] + args.refs + ["--out-dir", "workspace/transcripts"],
        2: ["--title", args.title, "--transcript-dir", "workspace/transcripts",
            "--out-dir", "workspace/scripts", "--config", args.config],
        3: ["--config", args.config, "--script-dir", "workspace/scripts",
            "--slides-dir", "workspace/slides"],
        4: ["--slides-dir", "workspace/slides", "--manim-dir", "workspace/manim"],
        5: ["--config", args.config, "--script-dir", "workspace/scripts",
            "--images-dir", "workspace/images"],
        6: ["--config", args.config, "--script-dir", "workspace/scripts",
            "--stock-dir", "workspace/stock"],
        7: ["--config", args.config, "--script-dir", "workspace/scripts",
            "--sfx-dir", "workspace/sfx"],
        8: ["--config", args.config, "--slides-dir", "workspace/slides",
            "--audio-dir", "workspace/audio"],
        9: ["--config", args.config, "--slides-dir", "workspace/slides",
            "--audio-dir", "workspace/audio", "--manim-dir", "workspace/manim",
            "--images-dir", "workspace/images", "--sfx-dir", "workspace/sfx",
            "--stock-dir", "workspace/stock"],
    }

    for num, name, script in STAGES:
        if num < args.from_stage or num > args.to_stage:
            continue
        run_stage(script, stage_args[num], num, name)

    print(f"\n{'='*60}")
    print("  PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"\nOutputs:")
    print(f"  workspace/output/video_en.mp4")
    print(f"  workspace/output/video_ko.mp4")
    print(f"  workspace/scripts/script_en.md  (review/edit the script)")
    print(f"  workspace/scripts/script_ko.md")
    print()


if __name__ == "__main__":
    main()
