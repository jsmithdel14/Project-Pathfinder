import re
import time
from urllib.parse import urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Purdue-MSAI-Capstone-ProjectPathfinder (academic research)"
TIMEOUT_SEC = 15
MAX_BYTES = 3_000_000          # skip pages larger than ~3 MB
MIN_CHARS = 200                # below this the page is probably JS-rendered or empty
REQUEST_DELAY_SEC = 1.0        # used by scrape_many

# Tags that never hold company-description text.
JUNK_TAGS = ["script", "style", "noscript", "template", "svg", "iframe",
             "nav", "header", "footer", "form", "aside", "button"]


class ScrapeError(Exception):
    """Raised when a URL can't be turned into usable text."""


def _clean_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ScrapeError("empty url")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url          # PDL file has bare domains like "acme.com"
    parts = urlparse(url)
    if not parts.netloc or "." not in parts.netloc:
        raise ScrapeError(f"invalid url: {url}")
    return urlunparse(parts._replace(fragment=""))


def _allowed_by_robots(url: str, session: requests.Session) -> bool:
    """True if robots.txt allows us. If robots.txt can't be read, allow."""
    parts = urlparse(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        r = session.get(robots_url, timeout=TIMEOUT_SEC)
    except requests.RequestException:
        return True
    if r.status_code in (401, 403):
        return False                    # site asks automated clients to stay out
    if r.status_code != 200:
        return True                     # no robots.txt = no restrictions
    rp = RobotFileParser()
    rp.parse(r.text.splitlines())
    return rp.can_fetch(USER_AGENT, url)


def html_to_text(html, encoding: str | None = None) -> str:
    """Strip page chrome and return visible text, one block per line."""
    soup = BeautifulSoup(html, "html.parser", from_encoding=encoding if isinstance(html, bytes) else None)
    for tag in soup(JUNK_TAGS):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def scrape_text(url: str, respect_robots: bool = True,
                session: requests.Session | None = None) -> str:
    """Fetch `url` and return its visible text. Raises ScrapeError on failure."""
    url = _clean_url(url)
    s = session or requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"})

    if respect_robots and not _allowed_by_robots(url, s):
        raise ScrapeError("blocked by robots.txt")

    try:
        resp = s.get(url, timeout=TIMEOUT_SEC, stream=True)
    except requests.exceptions.SSLError:
        raise ScrapeError("ssl error")
    except requests.exceptions.Timeout:
        raise ScrapeError("timeout")
    except requests.RequestException as e:
        raise ScrapeError(f"request failed: {type(e).__name__}")

    with resp:
        if resp.status_code >= 400:
            raise ScrapeError(f"http {resp.status_code}")
        ctype = resp.headers.get("Content-Type", "").lower()
        if "html" not in ctype and "text" not in ctype:
            raise ScrapeError(f"not html ({ctype or 'unknown type'})")
        chunks, size = [], 0
        for chunk in resp.iter_content(65536):
            size += len(chunk)
            if size > MAX_BYTES:
                raise ScrapeError("page too large")
            chunks.append(chunk)
        raw = b"".join(chunks)
        m = re.search(r"charset=([\w-]+)", ctype)
        declared = m.group(1) if m else None

    text = html_to_text(raw, declared)
    if not text:
        raise ScrapeError("no text found")
    return text


def scrape_many(urls, delay: float = REQUEST_DELAY_SEC, **kwargs) -> list[dict]:
    """Run scrape_text over a list. Never raises; returns one row per URL."""
    rows, session = [], requests.Session()
    for i, url in enumerate(urls):
        if i:
            time.sleep(delay)
        try:
            text = scrape_text(url, session=session, **kwargs)
            rows.append({"url": url, "text": text, "error": None, "thin": len(text) < MIN_CHARS})
        except ScrapeError as e:
            rows.append({"url": url, "text": "", "error": str(e), "thin": False})
    return rows