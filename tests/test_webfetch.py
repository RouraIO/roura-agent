"""
Tests for the web fetch and search module.

© Roura.io
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import json

from roura_agent.tools.webfetch import (
    strip_html_tags,
    extract_links_from_html,
    fetch_url,
    decode_html_entities,
    search_duckduckgo,
    search_brave,
    search_searxng,
    WebFetchTool,
    WebSearchTool,
    web_fetch,
    web_search,
    fetch_webpage,
    search_web,
)


class TestStripHtmlTags:
    """Tests for strip_html_tags function."""

    def test_removes_script_tags(self):
        """Test script tags are removed."""
        html = "<p>Hello</p><script>alert('xss')</script><p>World</p>"
        result = strip_html_tags(html)
        assert "alert" not in result
        assert "Hello" in result
        assert "World" in result

    def test_removes_style_tags(self):
        """Test style tags are removed."""
        html = "<p>Hello</p><style>body { color: red; }</style><p>World</p>"
        result = strip_html_tags(html)
        assert "color" not in result
        assert "Hello" in result

    def test_removes_html_comments(self):
        """Test HTML comments are removed."""
        html = "<p>Hello</p><!-- comment --><p>World</p>"
        result = strip_html_tags(html)
        assert "comment" not in result

    def test_decodes_entities(self):
        """Test HTML entities are decoded."""
        html = "<p>Hello &amp; World &lt;3&gt;</p>"
        result = strip_html_tags(html)
        assert "&" in result
        assert "<3>" in result


class TestExtractLinksFromHtml:
    """Tests for extract_links_from_html function."""

    def test_extracts_links(self):
        """Test links are extracted."""
        html = '<a href="https://example.com">Example</a>'
        links = extract_links_from_html(html, "https://base.com")
        assert len(links) == 1
        assert links[0]["url"] == "https://example.com"
        assert links[0]["text"] == "Example"

    def test_resolves_relative_links(self):
        """Test relative links are resolved."""
        html = '<a href="/page.html">Page</a>'
        links = extract_links_from_html(html, "https://base.com/")
        assert links[0]["url"] == "https://base.com/page.html"

    def test_skips_javascript_links(self):
        """Test javascript links are skipped."""
        html = '<a href="javascript:void(0)">Click</a>'
        links = extract_links_from_html(html, "https://base.com")
        assert len(links) == 0

    def test_skips_anchor_links(self):
        """Test anchor-only links are skipped."""
        html = '<a href="#section">Section</a>'
        links = extract_links_from_html(html, "https://base.com")
        assert len(links) == 0


class TestDecodeHtmlEntities:
    """Tests for decode_html_entities function."""

    def test_decodes_amp(self):
        """Test &amp; is decoded."""
        assert decode_html_entities("&amp;") == "&"

    def test_decodes_lt_gt(self):
        """Test &lt; and &gt; are decoded."""
        assert decode_html_entities("&lt;tag&gt;") == "<tag>"

    def test_decodes_hex_entities(self):
        """Test hex entities are decoded."""
        assert decode_html_entities("&#x27;") == "'"


class TestWebFetchTool:
    """Tests for WebFetchTool."""

    def test_tool_properties(self):
        """Test tool properties."""
        tool = WebFetchTool()
        assert tool.name == "web.fetch"
        assert tool.requires_approval is False

    @patch("roura_agent.tools.webfetch.httpx.Client")
    def test_fetch_success(self, mock_client_class):
        """Test successful fetch."""
        mock_response = Mock()
        mock_response.text = "<html><body>Hello World</body></html>"
        mock_response.url = "https://example.com"
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}

        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        result = web_fetch.execute(url="https://example.com")
        assert result.success is True
        assert "Hello World" in result.output["content"]

    def test_fetch_invalid_scheme(self):
        """Test fetch with invalid URL scheme."""
        result = web_fetch.execute(url="ftp://example.com/file.txt")
        assert result.success is False
        assert "Invalid URL scheme" in result.error


class TestWebSearchTool:
    """Tests for WebSearchTool."""

    def test_tool_properties(self):
        """Test tool properties."""
        tool = WebSearchTool()
        assert tool.name == "web.search"
        assert tool.requires_approval is False

    @patch("roura_agent.tools.webfetch.httpx.Client")
    def test_search_duckduckgo_returns_results(self, mock_client_class):
        """Test DuckDuckGo search returns results."""
        # Mock HTML response
        mock_html = '''
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com">Example Title</a>
        <a class="result__snippet">Example snippet text</a>
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample2.com">Example 2</a>
        <a class="result__snippet">Another snippet</a>
        '''

        mock_response = Mock()
        mock_response.text = mock_html
        mock_response.raise_for_status = Mock()

        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        results = search_duckduckgo("test query", max_results=5)
        assert len(results) >= 1
        assert results[0]["title"] == "Example Title"
        assert results[0]["url"] == "https://example.com"

    @patch("roura_agent.tools.webfetch.search_duckduckgo")
    def test_search_auto_uses_duckduckgo(self, mock_ddg):
        """Test auto provider uses DuckDuckGo when no API keys."""
        mock_ddg.return_value = [
            {"title": "Test", "url": "https://test.com", "snippet": "Snippet"}
        ]

        result = web_search.execute(query="test", provider="auto")
        assert result.success is True
        assert result.output["provider"] == "duckduckgo"
        mock_ddg.assert_called_once()

    @patch.dict("os.environ", {"BRAVE_API_KEY": "test_key"})
    @patch("roura_agent.tools.webfetch.search_brave")
    def test_search_auto_prefers_brave(self, mock_brave):
        """Test auto provider prefers Brave when API key is set."""
        mock_brave.return_value = [
            {"title": "Brave Result", "url": "https://brave.com", "snippet": ""}
        ]

        result = web_search.execute(query="test", provider="auto")
        assert result.success is True
        assert result.output["provider"] == "brave"
        mock_brave.assert_called_once()

    def test_search_brave_requires_api_key(self):
        """Test Brave provider requires API key."""
        # Ensure no API key is set
        import os
        old_key = os.environ.pop("BRAVE_API_KEY", None)

        try:
            result = web_search.execute(query="test", provider="brave")
            assert result.success is False
            assert "BRAVE_API_KEY" in result.error
        finally:
            if old_key:
                os.environ["BRAVE_API_KEY"] = old_key

    def test_search_searxng_requires_url(self):
        """Test SearXNG provider requires URL."""
        import os
        old_url = os.environ.pop("SEARXNG_URL", None)

        try:
            result = web_search.execute(query="test", provider="searxng")
            assert result.success is False
            assert "SEARXNG_URL" in result.error
        finally:
            if old_url:
                os.environ["SEARXNG_URL"] = old_url

    def test_search_invalid_provider(self):
        """Test invalid provider returns error."""
        result = web_search.execute(query="test", provider="invalid")
        assert result.success is False
        assert "Unknown provider" in result.error

    def test_dry_run(self):
        """Test dry run output."""
        result = web_search.dry_run(query="test query", max_results=3)
        assert "test query" in result
        assert "3" in result


class TestSearchBrave:
    """Tests for search_brave function."""

    @patch("roura_agent.tools.webfetch.httpx.Client")
    def test_brave_search_parses_response(self, mock_client_class):
        """Test Brave search parses API response."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "web": {
                "results": [
                    {"title": "Result 1", "url": "https://r1.com", "description": "Desc 1"},
                    {"title": "Result 2", "url": "https://r2.com", "description": "Desc 2"},
                ]
            }
        }
        mock_response.raise_for_status = Mock()

        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        results = search_brave("test", "fake_api_key", max_results=5)
        assert len(results) == 2
        assert results[0]["title"] == "Result 1"
        assert results[0]["url"] == "https://r1.com"


class TestSearchSearxng:
    """Tests for search_searxng function."""

    @patch("roura_agent.tools.webfetch.httpx.Client")
    def test_searxng_search_parses_response(self, mock_client_class):
        """Test SearXNG search parses response."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "results": [
                {"title": "SearX Result", "url": "https://searx.com", "content": "Content"},
            ]
        }
        mock_response.raise_for_status = Mock()

        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        results = search_searxng("test", "https://searx.example.com", max_results=5)
        assert len(results) == 1
        assert results[0]["title"] == "SearX Result"


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    @patch("roura_agent.tools.webfetch.web_fetch")
    def test_fetch_webpage(self, mock_tool):
        """Test fetch_webpage calls web_fetch."""
        mock_tool.execute.return_value = Mock(success=True)

        fetch_webpage("https://example.com", extract_links=True)
        mock_tool.execute.assert_called_once_with(url="https://example.com", extract_links=True)

    @patch("roura_agent.tools.webfetch.web_search")
    def test_search_web(self, mock_tool):
        """Test search_web calls web_search."""
        mock_tool.execute.return_value = Mock(success=True)

        search_web("test query", max_results=3, provider="duckduckgo")
        mock_tool.execute.assert_called_once_with(query="test query", max_results=3, provider="duckduckgo")
