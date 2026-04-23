import sys
import json
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "stages"))

from generate_images_helpers import build_prompt_request, parse_prompts


class TestBuildPromptRequest:
    def test_returns_string(self):
        result = build_prompt_request("A script about ancient history.", 6)
        assert isinstance(result, str)

    def test_contains_image_count(self):
        result = build_prompt_request("Some script text.", 5)
        assert "5" in result

    def test_contains_script_excerpt(self):
        script = "The Picts were a confederation of tribes in northern Scotland."
        result = build_prompt_request(script, 6)
        assert "Picts" in result

    def test_specifies_json_output(self):
        result = build_prompt_request("Script text.", 6)
        assert "JSON" in result

    def test_specifies_resolution(self):
        result = build_prompt_request("Script text.", 6)
        assert "1920" in result or "widescreen" in result.lower()

    def test_specifies_no_text(self):
        result = build_prompt_request("Script text.", 6)
        lower = result.lower()
        assert "no text" in lower or "without text" in lower or "no ui" in lower


class TestParsePrompts:
    def test_parses_json_array(self):
        response = json.dumps(["Prompt one", "Prompt two", "Prompt three"])
        result = parse_prompts(response, 3)
        assert result == ["Prompt one", "Prompt two", "Prompt three"]

    def test_extracts_json_from_markdown_block(self):
        response = '```json\n["A dark castle", "A misty highland"]\n```'
        result = parse_prompts(response, 2)
        assert result == ["A dark castle", "A misty highland"]

    def test_truncates_to_image_count(self):
        prompts = [f"Prompt {i}" for i in range(10)]
        response = json.dumps(prompts)
        result = parse_prompts(response, 6)
        assert len(result) == 6

    def test_raises_on_empty_list(self):
        import pytest
        with pytest.raises(ValueError, match="No prompts"):
            parse_prompts("[]", 6)

    def test_strips_whitespace_from_prompts(self):
        response = json.dumps(["  A foggy moor  ", "  Ancient stones  "])
        result = parse_prompts(response, 2)
        assert result == ["A foggy moor", "Ancient stones"]
