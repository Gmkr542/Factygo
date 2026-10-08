from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from app.schemas.investigation import Source


class ResearchService:
    """Free web research adapter using DuckDuckGo HTML + direct page retrieval."""

    SEARCH_URL = "https://html.duckduckgo.com/html/"
    TIMEOUT = httpx.Timeout(12.0, connect=8.0)
    MAX_RESULTS = 10
    MAX_PAGE_CHARS = 18000

    HIGH_AUTHORITY = {
        "nasa.gov", "noaa.gov", "usgs.gov", "nih.gov", "cdc.gov", "who.int",
        "un.org", "worldbank.org", "imf.org", "ec.europa.eu", "supremecourt.gov",
        "eci.gov.in", "indiacode.nic.in", "pib.gov.in", "isro.gov.in", "rbi.org.in",
        "mospi.gov.in", "mha.gov.in", "mea.gov.in", "gov.in", "nic.in",
    }
    ACADEMIC_DOMAINS = {"edu", "ac.in"}
    REPUTABLE_NEWS = {
        "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "thehindu.com",
        "indianexpress.com", "nytimes.com", "washingtonpost.com", "theguardian.com",
    }

    def search(self, query: str) -> list[dict]:
        queries = self._build_queries(query)
        documents: list[dict] = []
        seen: set[str] = set()
        headers = {"User-Agent": "Factygo/1.1 (+evidence-research)"}

        with httpx.Client(timeout=self.TIMEOUT, follow_redirects=True, headers=headers) as client:
            for search_query in queries:
                try:
                    response = client.get(self.SEARCH_URL, params={"q": search_query})
                    response.raise_for_status()
                except httpx.HTTPError:
                    continue

                soup = BeautifulSoup(response.text, "html.parser")
                for result in soup.select(".result"):
                    link = result.select_one("a.result__a")
                    if not link:
                        continue
                    url = self._clean_url(link.get("href", ""))
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    title = link.get_text(" ", strip=True)
                    snippet_node = result.select_one(".result__snippet")
                    snippet = snippet_node.get_text(" ", strip=True) if snippet_node else ""
                    documents.append({
                        "title": title[:300],
                        "url": url,
                        "snippet": snippet[:1000],
                        "source_score": self._source_score(url),
                        "source_type": self._source_type(url),
                        "source_tier": self._source_tier(url),
                    })
                    if len(documents) >= self.MAX_RESULTS:
                        break
                if len(documents) >= self.MAX_RESULTS:
                    break

            for document in documents:
                page_text = self._fetch_page(client, document["url"])
                document["text"] = page_text or document.get("snippet", "")
                document["retrieved"] = bool(document["text"])

        documents.sort(key=lambda d: (d["source_score"], d.get("retrieved", False)), reverse=True)
        return [d for d in documents if d.get("retrieved")]

    def normalize(self, documents: list[dict]) -> list[Source]:
        return [
            Source(
                title=doc.get("title", "Untitled"),
                url=doc.get("url", ""),
                domain=urlparse(doc.get("url", "")).netloc.lower().removeprefix("www."),
                source_score=float(doc.get("source_score", 0)),
                source_type=doc.get("source_type", "unknown"),
                source_tier=int(doc.get("source_tier", 5)),
            )
            for doc in documents
        ]

    def _build_queries(self, claim: str) -> list[str]:
        clean = re.sub(r"\s+", " ", claim).strip()
        return [clean, f"{clean} evidence", f"{clean} official source", f"{clean} scientific research"]

    @staticmethod
    def _clean_url(raw: str) -> str:
        if raw.startswith("//"):
            raw = "https:" + raw
        parsed = urlparse(raw)
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            target = parse_qs(parsed.query).get("uddg", [""])[0]
            return unquote(target)
        return raw if parsed.scheme in {"http", "https"} else ""

    def _fetch_page(self, client: httpx.Client, url: str) -> str:
        try:
            response = client.get(url)
            response.raise_for_status()
            if "text/html" not in response.headers.get("content-type", ""):
                return ""
            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(" ", strip=True)
            return re.sub(r"\s+", " ", text)[: self.MAX_PAGE_CHARS]
        except (httpx.HTTPError, UnicodeError):
            return ""

    @classmethod
    def _source_type(cls, url: str) -> str:
        domain = urlparse(url).netloc.lower().removeprefix("www.")
        if cls._source_tier(url) == 1:
            return "official"
        if cls._source_tier(url) == 2:
            return "academic"
        if domain in cls.REPUTABLE_NEWS or any(domain.endswith("." + d) for d in cls.REPUTABLE_NEWS):
            return "news"
        return "web"

    @classmethod
    def _source_tier(cls, url: str) -> int:
        domain = urlparse(url).netloc.lower().removeprefix("www.")
        if domain in cls.HIGH_AUTHORITY or any(domain.endswith("." + d) for d in cls.HIGH_AUTHORITY if "." in d):
            return 1
        suffix = "." + domain.split(".")[-1] if "." in domain else domain
        if suffix in {".edu", ".ac.in"} or domain.endswith(".edu") or domain.endswith(".ac.in"):
            return 2
        if domain in cls.REPUTABLE_NEWS or any(domain.endswith("." + d) for d in cls.REPUTABLE_NEWS):
            return 3
        return 4

    @classmethod
    def _source_score(cls, url: str) -> float:
        return {1: 1.0, 2: 0.9, 3: 0.8, 4: 0.5}[cls._source_tier(url)]
