from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from app.schemas.investigation import Source


class ResearchService:
    """Free web research adapter using DuckDuckGo HTML + direct page retrieval.

    No paid search API is required. Provider-specific logic stays here so it can
    later be replaced by another adapter without changing the investigation API.
    """

    SEARCH_URL = "https://html.duckduckgo.com/html/"
    TIMEOUT = httpx.Timeout(12.0, connect=8.0)
    MAX_RESULTS = 8
    MAX_PAGE_CHARS = 18000

    def search(self, query: str) -> list[dict]:
        queries = self._build_queries(query)
        documents: list[dict] = []
        seen: set[str] = set()

        headers = {"User-Agent": "Factygo/1.0 (+evidence-research)"}
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
                    })
                    if len(documents) >= self.MAX_RESULTS:
                        break
                if len(documents) >= self.MAX_RESULTS:
                    break

            for document in documents:
                page_text = self._fetch_page(client, document["url"])
                document["text"] = page_text
                document["retrieved"] = bool(page_text)

        return [d for d in documents if d.get("retrieved")]

    def normalize(self, documents: list[dict]) -> list[Source]:
        return [
            Source(
                title=doc.get("title", "Untitled"),
                url=doc.get("url", ""),
                domain=urlparse(doc.get("url", "")).netloc,
                source_score=float(doc.get("source_score", 0)),
                source_type=doc.get("source_type", "unknown"),
            )
            for doc in documents
        ]

    def _build_queries(self, claim: str) -> list[str]:
        clean = re.sub(r"\s+", " ", claim).strip()
        return [clean, f"{clean} facts", f"{clean} official"]

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
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type:
                return ""
            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
                tag.decompose()
            text = soup.get_text(" ", strip=True)
            return re.sub(r"\s+", " ", text)[: self.MAX_PAGE_CHARS]
        except (httpx.HTTPError, UnicodeError):
            return ""

    @staticmethod
    def _source_type(url: str) -> str:
        domain = urlparse(url).netloc.lower().removeprefix("www.")
        if domain.endswith(".gov") or domain.endswith(".gov.in") or domain.endswith(".nic.in"):
            return "official"
        if domain.endswith(".edu") or domain.endswith(".ac.in"):
            return "academic"
        if any(x in domain for x in ("reuters.com", "apnews.com", "bbc.com", "thehindu.com", "indianexpress.com")):
            return "news"
        return "web"

    @staticmethod
    def _source_score(url: str) -> float:
        kind = ResearchService._source_type(url)
        return {"official": 1.0, "academic": 0.9, "news": 0.8, "web": 0.5}.get(kind, 0.3)
