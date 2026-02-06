"""
Web search module for localseek

Fetches web results to complement local search.
Uses DuckDuckGo HTML search (no API key required).
"""

import re
import urllib.request
import urllib.parse
from typing import List, Dict, Optional
from html import unescape


# DuckDuckGo HTML search URL
DDG_URL = "https://html.duckduckgo.com/html/"

# User agent to avoid blocks
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def fetch_web_results(
    query: str,
    max_results: int = 5,
    timeout: int = 10,
) -> List[Dict[str, str]]:
    """
    Fetch web search results from DuckDuckGo
    
    Args:
        query: Search query
        max_results: Maximum results to return
        timeout: Request timeout in seconds
    
    Returns:
        List of dicts with title, snippet, url
    """
    try:
        # Prepare request
        data = urllib.parse.urlencode({"q": query}).encode("utf-8")
        
        req = urllib.request.Request(
            DDG_URL,
            data=data,
            headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        
        with urllib.request.urlopen(req, timeout=timeout) as response:
            html = response.read().decode("utf-8", errors="ignore")
        
        return _parse_ddg_html(html, max_results)
        
    except Exception as e:
        # Fail silently - web search is optional
        import sys
        print(f"Warning: Web search failed: {e}", file=sys.stderr)
        return []


def _parse_ddg_html(html: str, max_results: int) -> List[Dict[str, str]]:
    """Parse DuckDuckGo HTML results"""
    results = []
    
    # Find result blocks: <div class="result...">
    # Each result has:
    # - <a class="result__a" href="...">title</a>
    # - <a class="result__snippet">snippet</a>
    
    # Pattern for result links
    link_pattern = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>',
        re.IGNORECASE | re.DOTALL
    )
    
    # Pattern for snippets
    snippet_pattern = re.compile(
        r'<a[^>]*class="result__snippet"[^>]*>([^<]+(?:<[^>]+>[^<]*</[^>]+>)?[^<]*)</a>',
        re.IGNORECASE | re.DOTALL
    )
    
    # Alternative simpler patterns for DDG HTML
    # Sometimes format changes, so we try multiple approaches
    
    # Find all result divs
    result_divs = re.findall(
        r'<div[^>]*class="[^"]*result[^"]*"[^>]*>(.*?)</div>\s*</div>',
        html,
        re.IGNORECASE | re.DOTALL
    )
    
    if not result_divs:
        # Try alternative pattern
        result_divs = re.findall(
            r'<div[^>]*class="result[^"]*"[^>]*>(.*?)<div[^>]*class="result',
            html,
            re.IGNORECASE | re.DOTALL
        )
    
    for div in result_divs[:max_results * 2]:  # Get extra in case some fail
        if len(results) >= max_results:
            break
            
        # Extract URL and title
        link_match = link_pattern.search(div)
        if not link_match:
            continue
            
        url = link_match.group(1)
        title = _clean_html(link_match.group(2))
        
        # Skip DuckDuckGo internal links
        if "duckduckgo.com" in url:
            continue
        
        # Extract actual URL from DDG redirect
        if "/l/?uddg=" in url:
            url_match = re.search(r'uddg=([^&]+)', url)
            if url_match:
                url = urllib.parse.unquote(url_match.group(1))
        
        # Extract snippet
        snippet_match = snippet_pattern.search(div)
        snippet = _clean_html(snippet_match.group(1)) if snippet_match else ""
        
        if title and url:
            results.append({
                "title": title[:200],
                "snippet": snippet[:300],
                "url": url,
                "source": "web",
            })
    
    return results[:max_results]


def _clean_html(text: str) -> str:
    """Remove HTML tags and clean text"""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Unescape HTML entities
    text = unescape(text)
    # Normalize whitespace
    text = ' '.join(text.split())
    return text.strip()


def fetch_page_content(url: str, timeout: int = 10, max_chars: int = 5000) -> Optional[str]:
    """
    Fetch and extract main content from a web page
    
    Args:
        url: URL to fetch
        timeout: Request timeout
        max_chars: Maximum characters to return
    
    Returns:
        Extracted text content or None
    """
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT},
            method="GET",
        )
        
        with urllib.request.urlopen(req, timeout=timeout) as response:
            html = response.read().decode("utf-8", errors="ignore")
        
        # Extract text from body
        body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.IGNORECASE | re.DOTALL)
        if not body_match:
            return None
        
        body = body_match.group(1)
        
        # Remove scripts, styles, nav, footer
        for tag in ['script', 'style', 'nav', 'footer', 'header', 'aside']:
            body = re.sub(rf'<{tag}[^>]*>.*?</{tag}>', '', body, flags=re.IGNORECASE | re.DOTALL)
        
        # Extract paragraphs
        paragraphs = re.findall(r'<p[^>]*>([^<]+(?:<[^>]+>[^<]*</[^>]+>)?[^<]*)</p>', body, re.IGNORECASE)
        
        text = ' '.join(_clean_html(p) for p in paragraphs)
        
        if len(text) < 100:
            # Fallback: just clean all HTML
            text = _clean_html(body)
        
        return text[:max_chars] if text else None
        
    except Exception:
        return None
