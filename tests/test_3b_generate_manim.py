# tests/test_3b_generate_manim.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "stages"))

import pytest
from generate_manim_helpers import extract_bullets, estimate_duration, build_scene_code


class TestExtractBullets:
    def test_returns_at_most_4_bullets(self):
        narration = "Sentence one. Sentence two. Sentence three. Sentence four. Sentence five. Sentence six."
        bullets = extract_bullets(narration, max_bullets=4)
        assert len(bullets) <= 4

    def test_truncates_long_sentences_to_12_words(self):
        long = "This is a very long sentence that has way more than twelve words in it total."
        bullets = extract_bullets(long, max_bullets=1)
        assert len(bullets[0].split()) <= 13  # 12 words + "..."

    def test_returns_at_least_one_bullet(self):
        bullets = extract_bullets("Just one sentence.", max_bullets=4)
        assert len(bullets) == 1

    def test_empty_narration_returns_empty_list(self):
        bullets = extract_bullets("", max_bullets=4)
        assert bullets == []


class TestEstimateDuration:
    def test_130_words_equals_60_seconds(self):
        narration = " ".join(["word"] * 130)
        assert abs(estimate_duration(narration) - 60.0) < 0.1

    def test_zero_words_returns_zero(self):
        assert estimate_duration("") == 0.0

    def test_65_words_equals_30_seconds(self):
        narration = " ".join(["word"] * 65)
        assert abs(estimate_duration(narration) - 30.0) < 0.1


class TestBuildSceneCode:
    def test_output_is_valid_python(self):
        import ast
        code = build_scene_code(
            headline="Who Were the Picts?",
            bullets=["Bullet one.", "Bullet two."],
            duration=45.0,
        )
        ast.parse(code)  # raises SyntaxError if invalid

    def test_headline_embedded_in_code(self):
        code = build_scene_code("My Headline", [], 10.0)
        assert "My Headline" in code

    def test_special_chars_do_not_break_code(self):
        import ast
        code = build_scene_code('It\'s "complex"', ["Don't stop."], 30.0)
        ast.parse(code)
