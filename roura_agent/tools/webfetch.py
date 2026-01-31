"""
Roura Agent Web Fetch Tool - Fetch URLs and extract text content.

© Roura.io
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx

from .base import RiskLevel, Tool, ToolParam, ToolResult, registry

# Default timeout for requests
DEFAULT_TIMEOUT = 30.0

# Maximum content size (10MB)
MAX_CONTENT_SIZE = 10 * 1024 * 1024

# User agent for requests
USER_AGENT = "Roura-Agent/1.0 (https://roura.io)"


def strip_html_tags(html: str) -> str:
    """
    Strip HTML tags and extract text content.

    Args:
        html: HTML content

    Returns:
        Plain text content
    """
    # Remove script and style elements
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

    # Remove HTML comments
    html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)

    # Replace common block elements with newlines
    html = re.sub(r'<(?:p|div|br|h[1-6]|li|tr)[^>]*>', '\n', html, flags=re.IGNORECASE)

    # Remove remaining HTML tags
    html = re.sub(r'<[^>]+>', '', html)

    # Decode common HTML entities
    html = html.replace('&nbsp;', ' ')
    html = html.replace('&lt;', '<')
    html = html.replace('&gt;', '>')
    html = html.replace('&amp;', '&')
    html = html.replace('&quot;', '"')
    html = html.replace('&#39;', "'")

    # Clean up whitespace
    lines = []
    for line in html.split('\n'):
        line = ' '.join(line.split())  # Normalize whitespace
        if line:
            lines.append(line)

    return '\n'.join(lines)


def extract_links_from_html(html: str, base_url: str) -> list[dict]:
    """
    Extract links from HTML content.

    Args:
        html: HTML content
        base_url: Base URL for resolving relative links

    Returns:
        List of link dictionaries with 'url' and 'text' keys
    """
    links = []
    pattern = r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>'

    for match in re.finditer(pattern, html, re.IGNORECASE | re.DOTALL):
        href = match.group(1)
        text = strip_html_tags(match.group(2)).strip()

        # Skip empty or anchor-only links
        if not href or href.startswith('#') or href.startswith('javascript:'):
            continue

        # Resolve relative URLs
        try:
            full_url = urljoin(base_url, href)
            links.append({
                'url': full_url,
                'text': text[:100] if text else None,
            })
        except Exception:
            continue

    return links[:50]  # Limit to 50 links


def fetch_url(
    url: str,
    timeout: float = DEFAULT_TIMEOUT,
    extract_links: bool = False,
) -> dict:
    """
    Fetch a URL and return its content.

    Args:
        url: The URL to fetch
        timeout: Request timeout in seconds
        extract_links: Whether to extract links from HTML

    Returns:
        Dictionary with 'content', 'content_type', 'status_code', etc.
    """
    # Validate URL
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        raise ValueError(f"Invalid URL scheme: {parsed.scheme}")

    headers = {
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(url, headers=headers)

        content_type = response.headers.get('content-type', '').lower()
        content_length = int(response.headers.get('content-length', 0))

        # Check content size
        if content_length > MAX_CONTENT_SIZE:
            raise ValueError(f"Content too large: {content_length} bytes")

        # Get content
        raw_content = response.text

        # Process based on content type
        if 'application/json' in content_type:
            # Return JSON as-is
            return {
                'url': str(response.url),
                'status_code': response.status_code,
                'content_type': 'json',
                'content': raw_content[:50000],  # Limit size
                'links': [],
            }

        elif 'text/html' in content_type or 'application/xhtml' in content_type:
            # Extract text from HTML
            text_content = strip_html_tags(raw_content)

            result = {
                'url': str(response.url),
                'status_code': response.status_code,
                'content_type': 'html',
                'content': text_content[:50000],  # Limit size
                'links': [],
            }

            if extract_links:
                result['links'] = extract_links_from_html(raw_content, str(response.url))

            return result

        else:
            # Plain text or other
            return {
                'url': str(response.url),
                'status_code': response.status_code,
                'content_type': 'text',
                'content': raw_content[:50000],  # Limit size
                'links': [],
            }


@dataclass
class WebFetchTool(Tool):
    """Fetch a URL and extract text content."""

    name: str = "web.fetch"
    description: str = "Fetch a URL and extract text content (useful for documentation, APIs, etc.)"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("url", str, "The URL to fetch", required=True),
        ToolParam("extract_links", bool, "Whether to extract links from the page (default: False)", required=False, default=False),
    ])

    def execute(
        self,
        url: str,
        extract_links: bool = False,
    ) -> ToolResult:
        """Fetch a URL and extract content."""
        try:
            result = fetch_url(
                url=url,
                extract_links=extract_links,
            )

            return ToolResult(
                success=True,
                output={
                    'url': result['url'],
                    'status_code': result['status_code'],
                    'content_type': result['content_type'],
                    'content_length': len(result['content']),
                    'content': result['content'],
                    'links': result['links'] if extract_links else [],
                },
            )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                output=None,
                error="Request timed out",
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"HTTP error: {e.response.status_code}",
            )
        except ValueError as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
            )

    def dry_run(self, url: str, extract_links: bool = False) -> str:
        """Describe what would be fetched."""
        return f"Would fetch: {url}"


def decode_html_entities(text: str) -> str:
    """Decode HTML entities in a string."""
    import html
    return html.unescape(text)


def search_duckduckgo(query: str, max_results: int = 5) -> list[dict]:
    """
    Search DuckDuckGo and extract results.

    Uses the HTML search page (no API key required).

    Args:
        query: Search query
        max_results: Maximum number of results

    Returns:
        List of result dictionaries with 'title', 'url', 'snippet'
    """
    import urllib.parse

    # DuckDuckGo HTML search URL
    search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        response = client.get(search_url, headers=headers)
        response.raise_for_status()
        html = response.text

    results = []

    # Extract individual result components
    # Link pattern: <a class="result__a" href="URL">Title</a>
    link_pattern = re.compile(
        r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE
    )
    # Snippet pattern: <a class="result__snippet" ...>Snippet</a>
    snippet_pattern = re.compile(
        r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE
    )

    # Get all snippets first
    all_snippets = list(snippet_pattern.finditer(html))
    snippet_idx = 0

    # Find all result links
    for match in link_pattern.finditer(html):
        if len(results) >= max_results:
            break

        raw_url = decode_html_entities(match.group(1))
        title = strip_html_tags(match.group(2)).strip()

        # Skip ad/sponsored results and empty titles
        if not raw_url or not title:
            continue

        # DuckDuckGo wraps URLs in a redirect - extract the actual URL
        url = raw_url
        if '//duckduckgo.com/l/?' in raw_url:
            # Parse the redirect URL
            parsed_url = urllib.parse.urlparse(raw_url)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            if 'uddg' in query_params:
                url = urllib.parse.unquote(query_params['uddg'][0])
            else:
                continue  # Skip if can't extract real URL

        # Skip non-http URLs
        if not url.startswith('http'):
            continue

        # Get corresponding snippet
        snippet = ""
        if snippet_idx < len(all_snippets):
            snippet = strip_html_tags(all_snippets[snippet_idx].group(1)).strip()
            snippet_idx += 1

        results.append({
            'title': title[:200],
            'url': url,
            'snippet': snippet[:500] if snippet else "",
        })

    return results


def search_brave(query: str, api_key: str, max_results: int = 5) -> list[dict]:
    """
    Search using Brave Search API.

    Args:
        query: Search query
        api_key: Brave Search API key
        max_results: Maximum number of results

    Returns:
        List of result dictionaries
    """
    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        'Accept': 'application/json',
        'X-Subscription-Token': api_key,
    }
    params = {
        'q': query,
        'count': min(max_results, 20),
    }

    with httpx.Client(timeout=15.0) as client:
        response = client.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

    results = []
    for item in data.get('web', {}).get('results', [])[:max_results]:
        results.append({
            'title': item.get('title', ''),
            'url': item.get('url', ''),
            'snippet': item.get('description', ''),
        })

    return results


def search_searxng(query: str, instance_url: str, max_results: int = 5) -> list[dict]:
    """
    Search using a SearXNG instance.

    Args:
        query: Search query
        instance_url: SearXNG instance URL
        max_results: Maximum number of results

    Returns:
        List of result dictionaries
    """
    # Clean instance URL
    instance_url = instance_url.rstrip('/')
    search_url = f"{instance_url}/search"

    params = {
        'q': query,
        'format': 'json',
        'engines': 'google,bing,duckduckgo',
    }

    with httpx.Client(timeout=15.0) as client:
        response = client.get(search_url, params=params)
        response.raise_for_status()
        data = response.json()

    results = []
    for item in data.get('results', [])[:max_results]:
        results.append({
            'title': item.get('title', ''),
            'url': item.get('url', ''),
            'snippet': item.get('content', ''),
        })

    return results


@dataclass
class WebSearchTool(Tool):
    """
    Search the web using multiple providers.

    Providers (in order of preference):
    1. Brave Search API (if BRAVE_API_KEY is set)
    2. SearXNG instance (if SEARXNG_URL is set)
    3. DuckDuckGo HTML (no API key required, default)
    """

    name: str = "web.search"
    description: str = "Search the web and return relevant results"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("query", str, "Search query", required=True),
        ToolParam("max_results", int, "Maximum results (default: 5)", required=False, default=5),
        ToolParam("provider", str, "Search provider: auto, duckduckgo, brave, searxng (default: auto)", required=False, default="auto"),
    ])

    def execute(
        self,
        query: str,
        max_results: int = 5,
        provider: str = "auto",
    ) -> ToolResult:
        """Search the web."""
        import os

        max_results = min(max(1, max_results), 20)  # Clamp to 1-20

        try:
            results = []
            used_provider = ""

            if provider == "auto":
                # Try providers in order of preference
                brave_key = os.getenv('BRAVE_API_KEY')
                searxng_url = os.getenv('SEARXNG_URL')

                if brave_key:
                    results = search_brave(query, brave_key, max_results)
                    used_provider = "brave"
                elif searxng_url:
                    results = search_searxng(query, searxng_url, max_results)
                    used_provider = "searxng"
                else:
                    results = search_duckduckgo(query, max_results)
                    used_provider = "duckduckgo"

            elif provider == "duckduckgo":
                results = search_duckduckgo(query, max_results)
                used_provider = "duckduckgo"

            elif provider == "brave":
                brave_key = os.getenv('BRAVE_API_KEY')
                if not brave_key:
                    return ToolResult(
                        success=False,
                        output=None,
                        error="Brave Search requires BRAVE_API_KEY environment variable",
                    )
                results = search_brave(query, brave_key, max_results)
                used_provider = "brave"

            elif provider == "searxng":
                searxng_url = os.getenv('SEARXNG_URL')
                if not searxng_url:
                    return ToolResult(
                        success=False,
                        output=None,
                        error="SearXNG requires SEARXNG_URL environment variable",
                    )
                results = search_searxng(query, searxng_url, max_results)
                used_provider = "searxng"

            else:
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Unknown provider: {provider}. Use: auto, duckduckgo, brave, searxng",
                )

            return ToolResult(
                success=True,
                output={
                    'query': query,
                    'provider': used_provider,
                    'count': len(results),
                    'results': results,
                },
            )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                output=None,
                error="Search request timed out",
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Search HTTP error: {e.response.status_code}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Search failed: {str(e)}",
            )

    def dry_run(self, query: str, max_results: int = 5, provider: str = "auto") -> str:
        return f"Would search for: {query} (provider: {provider}, max_results: {max_results})"


# Create and register tool instances
web_fetch = WebFetchTool()
web_search = WebSearchTool()

registry.register(web_fetch)
registry.register(web_search)


# Convenience functions
def fetch_webpage(url: str, extract_links: bool = False) -> ToolResult:
    """Fetch a URL and extract text content."""
    return web_fetch.execute(url=url, extract_links=extract_links)


def search_web(query: str, max_results: int = 5, provider: str = "auto") -> ToolResult:
    """Search the web and return results."""
    return web_search.execute(query=query, max_results=max_results, provider=provider)
