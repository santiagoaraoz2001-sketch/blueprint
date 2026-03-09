"""Web Scraper — extract text content from web pages with crawling, format control, and robots.txt support."""

import json
import os
import re
import time
import urllib.request
import urllib.error
import urllib.robotparser
from collections import deque
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse


class _TextExtractor(HTMLParser):
    """Simple HTML-to-text parser using stdlib."""
    def __init__(self):
        super().__init__()
        self._text = []
        self._skip = False
        self._skip_tags = {"script", "style", "noscript", "svg", "head"}

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._skip_tags:
            self._skip = True
        if tag.lower() in ("br", "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"):
            self._text.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in self._skip_tags:
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            stripped = data.strip()
            if stripped:
                self._text.append(stripped)

    def get_text(self):
        return "\n".join(self._text)


class _LinkExtractor(HTMLParser):
    """Extract href links from HTML."""
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self.links.append(value)


def _check_robots(url, user_agent):
    """Check if URL is allowed by robots.txt."""
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(user_agent, url)
    except Exception:
        return True  # If we can't read robots.txt, allow


def _fetch_page(url, timeout, user_agent, cookies=""):
    """Fetch a single page and return (html, encoding)."""
    ua = user_agent or "Mozilla/5.0 (Blueprint Scraper/1.0)"
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,*/*",
    }
    if cookies:
        # Support both raw cookie string and JSON key=value pairs
        if cookies.strip().startswith("{"):
            try:
                cookie_dict = json.loads(cookies)
                headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookie_dict.items())
            except json.JSONDecodeError:
                headers["Cookie"] = cookies
        else:
            headers["Cookie"] = cookies
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        html_bytes = resp.read()
        encoding = resp.headers.get_content_charset() or "utf-8"
        return html_bytes.decode(encoding, errors="replace")


def _extract_content(html, selector, use_bs4):
    """Extract text and title from HTML."""
    if use_bs4:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        if selector and selector != "body":
            elements = soup.select(selector)
            text = "\n".join(el.get_text(separator=" ", strip=True) for el in elements)
        else:
            text = soup.get_text(separator="\n", strip=True)
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
    else:
        parser = _TextExtractor()
        parser.feed(html)
        text = parser.get_text()
        title = ""
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if title_match:
            title = title_match.group(1).strip()

    # Clean whitespace
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(line for line in lines if line)
    return text, title


def _extract_links(html, base_url):
    """Extract absolute links from HTML."""
    parser = _LinkExtractor()
    parser.feed(html)
    links = []
    for href in parser.links:
        absolute = urljoin(base_url, href)
        # Only keep http(s) links
        if absolute.startswith(("http://", "https://")):
            links.append(absolute)
    return links


def _format_result(url, title, text, include_metadata, output_format):
    """Format a single scrape result."""
    if output_format == "markdown":
        formatted_text = f"# {title}\n\n{text}" if title else text
    elif output_format == "raw_text":
        formatted_text = text
    else:
        formatted_text = text

    result = {"text": formatted_text}
    if include_metadata:
        result["url"] = url
        result["title"] = title
        result["char_count"] = len(text)
        result["word_count"] = len(text.split())
    return result


def run(ctx):
    urls_str = ctx.config.get("urls", "")
    selector = ctx.config.get("selector", "body")
    max_pages = int(ctx.config.get("max_pages", 10))
    timeout = int(ctx.config.get("timeout", 30))
    browse_mode = ctx.config.get("browse_mode", "static")
    follow_link_pattern = ctx.config.get("follow_link_pattern", "")
    max_depth = int(ctx.config.get("max_depth", 2))
    output_format = ctx.config.get("output_format", "structured_json")
    include_metadata = ctx.config.get("include_metadata", True)
    user_agent = ctx.config.get("user_agent", "")
    respect_robots = ctx.config.get("respect_robots", True)
    use_llm_extraction = ctx.config.get("use_llm_extraction", False)
    extraction_prompt = ctx.config.get("extraction_prompt", "")
    delay_ms = int(ctx.config.get("delay_ms", 0))
    exclude_url_pattern = ctx.config.get("exclude_url_pattern", "")
    cookies = ctx.config.get("cookies", "")

    # Apply overrides from connected config input
    try:
        _ci = ctx.load_input("config")
        if _ci:
            _ov = json.load(open(_ci)) if isinstance(_ci, str) and os.path.isfile(_ci) else (_ci if isinstance(_ci, dict) else {})
            if isinstance(_ov, dict) and _ov:
                ctx.log_message(f"Applying {len(_ov)} config override(s) from input")
                if "urls" in _ov:
                    urls_str = _ov["urls"] if isinstance(_ov["urls"], str) else "\n".join(_ov["urls"])
                selector = _ov.get("selector", selector)
                max_pages = int(_ov.get("max_pages", max_pages))
                cookies = _ov.get("cookies", cookies)
    except (ValueError, KeyError):
        pass

    # Normalize booleans
    if isinstance(include_metadata, str):
        include_metadata = include_metadata.lower() in ("true", "1", "yes")
    if isinstance(respect_robots, str):
        respect_robots = respect_robots.lower() in ("true", "1", "yes")
    if isinstance(use_llm_extraction, str):
        use_llm_extraction = use_llm_extraction.lower() in ("true", "1", "yes")

    if not urls_str:
        raise ValueError("urls is required — provide one or more URLs (one per line)")

    # Parse URLs — support both newline and comma separation for backward compat
    if "\n" in urls_str:
        urls = [u.strip() for u in urls_str.splitlines() if u.strip()]
    else:
        urls = [u.strip() for u in urls_str.split(",") if u.strip()]

    # Check for LLM extraction model
    if use_llm_extraction:
        try:
            model_input = ctx.load_input("model")
            ctx.log_message("LLM extraction model connected — feature available in future release")
        except (ValueError, KeyError):
            ctx.log_message("WARNING: LLM extraction enabled but no model connected. Falling back to CSS extraction.")
            use_llm_extraction = False

    # Try to use BeautifulSoup if available
    use_bs4 = False
    try:
        from bs4 import BeautifulSoup
        use_bs4 = True
        ctx.log_message("Using BeautifulSoup for parsing")
    except ImportError:
        ctx.log_message("bs4 not installed — using stdlib html.parser. Install: pip install beautifulsoup4")

    effective_ua = user_agent or "Mozilla/5.0 (Blueprint Scraper/1.0)"
    results = []
    visited = set()

    if browse_mode == "follow_links":
        # BFS crawl starting from seed URLs
        queue = deque()
        for url in urls:
            queue.append((url, 0))  # (url, depth)

        link_regex = re.compile(follow_link_pattern) if follow_link_pattern else None
        exclude_regex = re.compile(exclude_url_pattern) if exclude_url_pattern else None

        ctx.log_message(f"Crawling with follow_links mode (max_depth={max_depth}, max_pages={max_pages})")
        if exclude_url_pattern:
            ctx.log_message(f"Excluding URLs matching: {exclude_url_pattern}")

        while queue and len(results) < max_pages:
            current_url, depth = queue.popleft()

            if current_url in visited:
                continue
            visited.add(current_url)

            # Robots.txt check
            if respect_robots and not _check_robots(current_url, effective_ua):
                ctx.log_message(f"  Blocked by robots.txt: {current_url}")
                continue

            ctx.log_message(f"Scraping [{len(results)+1}/{max_pages}] (depth {depth}): {current_url}")

            try:
                html = _fetch_page(current_url, timeout, user_agent, cookies)
                text, title = _extract_content(html, selector, use_bs4)

                result = _format_result(current_url, title, text, include_metadata, output_format)
                results.append(result)
                ctx.log_message(f"  Extracted {len(text)} chars")

                # Extract and queue links if within depth
                if depth < max_depth:
                    links = _extract_links(html, current_url)
                    for link in links:
                        if link not in visited:
                            # Apply include pattern
                            if link_regex is not None and not link_regex.search(link):
                                continue
                            # Apply exclude pattern
                            if exclude_regex and exclude_regex.search(link):
                                continue
                            queue.append((link, depth + 1))

            except Exception as e:
                ctx.log_message(f"  Error scraping {current_url}: {e}")
                if include_metadata:
                    results.append({"url": current_url, "text": "", "error": str(e), "char_count": 0, "word_count": 0})

            # Politeness delay between requests
            if delay_ms > 0 and queue:
                time.sleep(delay_ms / 1000)

            ctx.report_progress(len(results), max_pages)

    else:
        # Static mode (or dynamic fallback to static)
        if browse_mode == "dynamic":
            ctx.log_message("NOTE: Dynamic mode (JavaScript rendering) requires playwright. Falling back to static.")
            ctx.log_message("Install with: pip install playwright && playwright install chromium")

        urls = urls[:max_pages]
        ctx.log_message(f"Scraping {len(urls)} URL(s) in static mode")

        for i, url in enumerate(urls):
            if url in visited:
                continue
            visited.add(url)

            # Robots.txt check
            if respect_robots and not _check_robots(url, effective_ua):
                ctx.log_message(f"  Blocked by robots.txt: {url}")
                continue

            ctx.log_message(f"Scraping [{i+1}/{len(urls)}]: {url}")

            try:
                html = _fetch_page(url, timeout, user_agent, cookies)
                text, title = _extract_content(html, selector, use_bs4)

                result = _format_result(url, title, text, include_metadata, output_format)
                results.append(result)
                ctx.log_message(f"  Extracted {len(text)} chars, {len(text.split())} words")

            except Exception as e:
                ctx.log_message(f"  Error scraping {url}: {e}")
                if include_metadata:
                    results.append({"url": url, "title": "", "text": "", "error": str(e), "char_count": 0, "word_count": 0})

            # Politeness delay between requests
            if delay_ms > 0 and i < len(urls) - 1:
                time.sleep(delay_ms / 1000)

            ctx.report_progress(i + 1, len(urls))

    # Save as dataset
    out_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "data.json")
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)

    ctx.save_output("dataset", out_dir)
    success_count = len([r for r in results if not r.get("error")])
    _total_chars = sum(r.get("char_count", len(r.get("text", ""))) for r in results)
    ctx.log_metric("pages_scraped", success_count)
    ctx.log_metric("total_chars", _total_chars)
    ctx.log_message(f"Scraping complete: {success_count}/{len(results)} pages successful.")
    ctx.report_progress(1, 1)

    # Save metrics output
    _metrics = {"pages_scraped": success_count, "pages_failed": len(results) - success_count, "total_chars": _total_chars, "urls_visited": len(visited), "output_format": output_format}
    _mp = os.path.join(ctx.run_dir, "metrics.json")
    with open(_mp, "w") as f:
        json.dump(_metrics, f, indent=2)
    ctx.save_output("metrics", _mp)
