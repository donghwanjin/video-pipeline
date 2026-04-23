"""
Pure helper functions for stage 3b: no Manim or subprocess imports.
Kept separate so they can be unit-tested without Manim installed.
"""
import re
import json


SCENE_TEMPLATE = '''\
from manim import *

ACCENT = ManimColor("#6366f1")
BG = ManimColor("#12121e")
BULLET_COLOR = ManimColor("#c8c8dc")


class CinematicSlide(Scene):
    HEADLINE = {headline}
    BULLETS = {bullets}
    NARRATION_DURATION = {duration}

    def construct(self):
        self.camera.background_color = BG

        # --- Phase 1: Cinematic intro (1.5s) ---
        bar = Rectangle(
            width=config.frame_width + 0.1,
            height=0.12,
            color=ACCENT,
            fill_color=ACCENT,
            fill_opacity=1,
            stroke_width=0,
        )
        bar.to_edge(UP, buff=1.8)
        bar.shift(LEFT * (config.frame_width + 0.1))

        headline = Text(self.HEADLINE, font_size=52, color=WHITE, weight=BOLD)
        headline.to_edge(UP, buff=2.2)
        headline.set_opacity(0)
        self.add(bar, headline)

        self.play(
            bar.animate.shift(RIGHT * (config.frame_width + 0.1)),
            headline.animate.set_opacity(1).shift(UP * 0.3),
            run_time=1.5,
        )
        self.wait(0.3)

        # --- Phase 2: Bullet reveal ---
        y_start = headline.get_bottom()[1] - 0.9
        bullet_rows = []
        for i, bullet_text in enumerate(self.BULLETS):
            dot = Dot(color=ACCENT, radius=0.08)
            text = Text(bullet_text, font_size=34, color=BULLET_COLOR)
            text.next_to(dot, RIGHT, buff=0.25)
            row = VGroup(dot, text)
            row.to_edge(LEFT, buff=1.2)
            row.set_y(y_start - i * 1.0)
            bullet_rows.append(row)

        time_per_bullet = self.NARRATION_DURATION / max(len(bullet_rows), 1)
        for i, row in enumerate(bullet_rows):
            self.play(FadeIn(row, shift=UP * 0.15), run_time=0.5)
            if i < len(bullet_rows) - 1:
                self.wait(max(time_per_bullet - 0.5, 0.1))

        # --- Phase 3: Hold ---
        self.wait(0.5)
'''


def extract_bullets(narration: str, max_bullets: int = 4) -> list[str]:
    """Extract up to max_bullets key sentences from narration text."""
    if not narration.strip():
        return []
    sentences = re.split(r"(?<=[.!?])\s+", narration.strip())
    sentences = [s.strip() for s in sentences if s.strip()]
    step = max(1, len(sentences) // max_bullets)
    selected = sentences[::step][:max_bullets]
    result = []
    for s in selected:
        words = s.split()
        if len(words) > 12:
            s = " ".join(words[:12]) + "..."
        result.append(s)
    return result


def estimate_duration(narration: str) -> float:
    """Estimate narration duration in seconds at 130 words per minute."""
    words = len(narration.split())
    return (words / 130) * 60 if words else 0.0


def build_scene_code(headline: str, bullets: list[str], duration: float) -> str:
    """Return a complete Manim scene Python file as a string."""
    return SCENE_TEMPLATE.format(
        headline=json.dumps(headline),
        bullets=json.dumps(bullets),
        duration=round(duration, 2),
    )
