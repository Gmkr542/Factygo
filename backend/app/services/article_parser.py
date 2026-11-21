import ipaddress
import socket
import urllib.robotparser
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.config import get_settings


class ArticleFetchError(Exception):
    pass


REDIRECT_STATUSES = {301, 302, 303, 307, 308}
MAX_REDIRECTS = 5
MAX_ROBOTS_BYTES = 512 * 1024


def _safe_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        if not infos:
            return False
        for item in infos:
            ip = ipaddress.ip_address(item[4][0])
            if not ip.is_global:
                return False
        return True
    except Exception:
        return False


def _public_http_url(url: str) -> bool:
    try:
        p = urlparse(url)
        if p.scheme not in {"http", "https"} or not p.hostname:
            return False
        if p.username is not None or p.password is not None:
            return False
        return _safe_host(p.hostname)
    except Exception:
        return False


async def _request_limited(url: str, ua: str, timeout: float, max_bytes: int):
    current = url
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False, headers={"User-Agent": ua}) as client:
        for hop in range(MAX_REDIRECTS + 1):
            if not _public_http_url(current):
                raise ArticleFetchError("URL or redirect target is not allowed")
            async with client.stream("GET", current) as response:
                if response.status_code in REDIRECT_STATUSES:
                    location = response.headers.get("location")
                    if not location or hop >= MAX_REDIRECTS:
                        raise ArticleFetchError("Redirect limit reached")
                    current = urljoin(current, location)
                    continue
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > max_bytes:
                        raise ArticleFetchError("Page too large")
                    body.extend(chunk)
                return response.status_code, response.headers, bytes(body), str(response.url)
    raise ArticleFetchError("Redirect limit reached")


async def fetch_article(url: str) -> tuple[str, str]:
    if not _public_http_url(url):
        raise ArticleFetchError("Invalid or non-public URL")
    settings = get_settings()
    ua = "Factygo/1.1"
    status, headers, body, final_url = await _request_limited(url, ua, settings.request_timeout, settings.max_article_chars * 20)
    if status >= 400 or not _public_http_url(final_url):
        raise ArticleFetchError("Unable to retrieve article")
    if "text/html" not in headers.get("content-type", "").lower():
        raise ArticleFetchError("URL is not an HTML page")
    soup = BeautifulSoup(body, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "form", "aside"]):
        tag.decompose()
    title_tag = soup.find("meta", property="og:title") or soup.title
    title = title_tag.get("content", "") if title_tag and title_tag.name == "meta" else (title_tag.get_text(" ", strip=True) if title_tag else "")
    article = soup.find("article") or soup.body
    text = " ".join(article.stripped_strings) if article else ""
    if not text.strip():
        raise ArticleFetchError("No readable article text found")
    return title[:500], text[:settings.max_article_chars]
