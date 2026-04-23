"""
Stage 4: Generate per-slide audio using ElevenLabs TTS.

Usage:
    python stages/4_generate_audio.py --config config.yaml

Reads:
    workspace/slides/slides_en.json
    workspace/slides/slides_ko.json

Outputs:
    workspace/audio/en/slide_01.mp3 ...
    workspace/audio/ko/slide_01.mp3 ...
"""

import argparse
import json
import os
import time

import yaml
from elevenlabs.client import ElevenLabs
from elevenlabs import VoiceSettings


def generate_audio_for_lang(
    client: ElevenLabs,
    metadata: list[dict],
    voice_id: str,
    out_dir: str,
    lang: str,
):
    os.makedirs(out_dir, exist_ok=True)
    total = len(metadata)

    for slide in metadata:
        i = slide["index"]
        narration = slide["narration"]
        out_path = os.path.join(out_dir, f"slide_{i:02d}.mp3")

        if os.path.exists(out_path):
            print(f"  [{lang}] slide {i:02d} already exists, skipping.")
            continue

        print(f"  [{lang}] Generating audio {i}/{total}...")
        audio_generator = client.text_to_speech.convert(
            voice_id=voice_id,
            text=narration,
            model_id="eleven_multilingual_v2",
            voice_settings=VoiceSettings(
                stability=0.5,
                similarity_boost=0.75,
                style=0.0,
                use_speaker_boost=True,
            ),
        )
        # Consume the generator and write bytes
        audio_bytes = b"".join(audio_generator)
        with open(out_path, "wb") as f:
            f.write(audio_bytes)
        print(f"    Saved {out_path} ({len(audio_bytes)} bytes)")

        # Rate-limit: avoid hammering the API
        if i < total:
            time.sleep(0.5)


def main():
    parser = argparse.ArgumentParser(description="Generate TTS audio via ElevenLabs")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--slides-dir", default="workspace/slides")
    parser.add_argument("--audio-dir", default="workspace/audio")
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    el_key = cfg.get("elevenlabs_api_key", "")
    if not el_key or el_key == "...":
        raise ValueError("Set your elevenlabs_api_key in config.yaml")

    voice_en = cfg.get("elevenlabs_voice_en", "")
    voice_ko = cfg.get("elevenlabs_voice_ko", "")

    client = ElevenLabs(api_key=el_key)

    print("[Stage 4] Generating English audio...")
    with open(os.path.join(args.slides_dir, "slides_en.json"), encoding="utf-8") as f:
        meta_en = json.load(f)
    generate_audio_for_lang(client, meta_en, voice_en, os.path.join(args.audio_dir, "en"), "en")

    if not voice_ko or voice_ko == "...":
        print("[Stage 4] Skipping Korean audio (elevenlabs_voice_ko not set).")
    else:
        print("[Stage 4] Generating Korean audio...")
        with open(os.path.join(args.slides_dir, "slides_ko.json"), encoding="utf-8") as f:
            meta_ko = json.load(f)
        generate_audio_for_lang(client, meta_ko, voice_ko, os.path.join(args.audio_dir, "ko"), "ko")

    print("[Stage 4] Done.")


if __name__ == "__main__":
    main()
