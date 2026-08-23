"""Tests for web_search response models (SearXNG JSON parsing)."""

import pytest

from crow_cli.mcp.web_search.main import Infobox, SearchResponse, SearchResult


class TestSearchModels:
    def test_parse_full_response(self):
        payload = {
            "query": "python",
            "results": [
                {"url": "https://python.org", "title": "Python", "content": "official"},
                {"url": "https://docs.python.org", "title": "Docs", "content": "ref"},
            ],
            "infoboxes": [
                {
                    "infobox": "Python",
                    "id": "Q1",
                    "content": "a language",
                    "urls": [{"title": "wiki", "url": "https://en.wikipedia.org"}],
                }
            ],
        }
        resp = SearchResponse.model_validate(payload)
        assert resp.query == "python"
        assert len(resp.results) == 2
        assert resp.results[0].title == "Python"
        assert len(resp.infoboxes) == 1
        assert resp.infoboxes[0].urls[0].title == "wiki"

    def test_parse_empty_results(self):
        resp = SearchResponse.model_validate(
            {"query": "x", "results": [], "infoboxes": []}
        )
        assert resp.results == []
        assert resp.infoboxes == []

    def test_search_result_missing_field_raises(self):
        with pytest.raises(Exception):
            SearchResult.model_validate({"url": "u", "title": "t"})  # no content

    def test_infobox_model(self):
        box = Infobox.model_validate(
            {"infobox": "X", "id": "1", "content": "c", "urls": []}
        )
        assert box.infobox == "X" and box.urls == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
