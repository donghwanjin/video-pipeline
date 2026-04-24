import sys
import json
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "stages"))

from generate_sfx_helpers import build_sfx_prompt, parse_cues, build_freesound_url


class TestBuildSfxPrompt:
    def test_returns_string(self):
        result = build_sfx_prompt("A script about ancient history.", 3)
        assert isinstance(result, str)

    def test_contains_sfx_count(self):
        result = build_sfx_prompt("Some script text.", 4)
        assert "4" in result

    def test_contains_script_text(self):
        script = "The Picts were a confederation of tribes."
        result = build_sfx_prompt(script, 3)
        assert "Picts" in result

    def test_specifies_json_output(self):
        result = build_sfx_prompt("Script text.", 3)
        assert "JSON" in result

    def test_specifies_slide_index_field(self):
        result = build_sfx_prompt("Script text.", 3)
        assert "slide_index" in result


class TestParseCues:
    def test_parses_plain_json(self):
        response = json.dumps([
            {"slide_index": 1, "cue": "whoosh intro"},
            {"slide_index": 3, "cue": "camera shutter"},
        ])
        result = parse_cues(response, 3)
        assert result == [
            {"slide_index": 1, "cue": "whoosh intro"},
            {"slide_index": 3, "cue": "camera shutter"},
        ]

    def test_parses_markdown_fenced_json(self):
        response = '```json\n[{"slide_index": 2, "cue": "typewriter"}]\n```'
        result = parse_cues(response, 3)
        assert result == [{"slide_index": 2, "cue": "typewriter"}]

    def test_raises_on_empty_array(self):
        with pytest.raises(ValueError, match="No cues"):
            parse_cues("[]", 3)

    def test_raises_on_non_list_json(self):
        with pytest.raises(ValueError, match="Expected JSON array"):
            parse_cues('{"slide_index": 1, "cue": "whoosh"}', 3)

    def test_truncates_to_sfx_count(self):
        cues = [{"slide_index": i, "cue": f"sound {i}"} for i in range(1, 8)]
        result = parse_cues(json.dumps(cues), 3)
        assert len(result) == 3

    def test_strips_whitespace_from_cue(self):
        response = json.dumps([{"slide_index": 1, "cue": "  camera click  "}])
        result = parse_cues(response, 3)
        assert result[0]["cue"] == "camera click"

    def test_skips_invalid_entries(self):
        response = json.dumps([
            "not a dict",
            {"slide_index": 2, "cue": "valid sound"},
            {"missing": "fields"},
        ])
        result = parse_cues(response, 3)
        assert result == [{"slide_index": 2, "cue": "valid sound"}]

    def test_raises_when_all_entries_invalid(self):
        response = json.dumps([{"wrong": "keys"}, 42, None])
        with pytest.raises(ValueError, match="No valid cues"):
            parse_cues(response, 3)


class TestBuildFreesoundUrl:
    def test_encodes_spaces_in_query(self):
        url = build_freesound_url("camera shutter click", "mykey123")
        assert "camera+shutter+click" in url

    def test_includes_api_key(self):
        url = build_freesound_url("whoosh", "mykey123")
        assert "mykey123" in url

    def test_targets_freesound(self):
        url = build_freesound_url("whoosh", "mykey123")
        assert "freesound.org" in url
