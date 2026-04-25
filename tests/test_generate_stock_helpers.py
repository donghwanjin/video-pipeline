import sys
import json
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "stages"))
from generate_stock_helpers import build_stock_prompt, parse_cues, build_pexels_url


class TestBuildStockPrompt:
    def test_returns_string(self):
        result = build_stock_prompt("A script about ancient history.", 3)
        assert isinstance(result, str)

    def test_contains_stock_count(self):
        result = build_stock_prompt("Some script text.", 4)
        assert "4" in result

    def test_contains_script_excerpt(self):
        script = "The Colosseum was built in Rome."
        result = build_stock_prompt(script, 3)
        assert "Colosseum" in result

    def test_specifies_json_output(self):
        result = build_stock_prompt("Script text.", 3)
        assert "JSON" in result

    def test_specifies_slide_index_and_keyword(self):
        result = build_stock_prompt("Script text.", 3)
        assert "slide_index" in result
        assert "keyword" in result


class TestParseCues:
    def test_parses_plain_json_array(self):
        response = json.dumps([{"slide_index": 1, "keyword": "roman forum"}])
        result = parse_cues(response, 3)
        assert result == [{"slide_index": 1, "keyword": "roman forum"}]

    def test_extracts_json_from_markdown_block(self):
        response = '```json\n[{"slide_index": 2, "keyword": "castle ruins"}]\n```'
        result = parse_cues(response, 3)
        assert result == [{"slide_index": 2, "keyword": "castle ruins"}]

    def test_truncates_to_stock_count(self):
        items = [{"slide_index": i, "keyword": f"keyword {i}"} for i in range(1, 6)]
        response = json.dumps(items)
        result = parse_cues(response, 3)
        assert len(result) == 3

    def test_raises_on_empty_array(self):
        with pytest.raises(ValueError, match="No cues"):
            parse_cues("[]", 3)

    def test_raises_on_non_list_json(self):
        with pytest.raises(ValueError, match="Expected JSON array"):
            parse_cues('{"slide_index": 1, "keyword": "test"}', 3)

    def test_raises_on_malformed_json(self):
        with pytest.raises(ValueError, match="not valid JSON"):
            parse_cues("not json at all", 3)

    def test_strips_whitespace_from_keyword(self):
        response = json.dumps([{"slide_index": 1, "keyword": "  roman ruins  "}])
        result = parse_cues(response, 3)
        assert result[0]["keyword"] == "roman ruins"

    def test_skips_entries_missing_required_fields(self):
        response = json.dumps([
            {"slide_index": 1},
            {"keyword": "test"},
            {"slide_index": 2, "keyword": "valid entry"},
        ])
        result = parse_cues(response, 3)
        assert result == [{"slide_index": 2, "keyword": "valid entry"}]

    def test_raises_when_all_entries_invalid(self):
        response = json.dumps([{"bad": "entry"}, {"also": "bad"}])
        with pytest.raises(ValueError, match="No valid cues"):
            parse_cues(response, 3)


class TestBuildPexelsUrl:
    def test_encodes_spaces_as_plus(self):
        url = build_pexels_url("ancient roman forum")
        assert "ancient+roman+forum" in url

    def test_includes_keyword(self):
        url = build_pexels_url("castle ruins")
        assert "castle+ruins" in url

    def test_targets_pexels(self):
        url = build_pexels_url("test")
        assert "api.pexels.com" in url
