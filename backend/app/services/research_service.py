from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from app.schemas.investigation import Source


class ResearchService:
    """Free web research with resilient search-result/snippet retrieval.

    Search snippets remain usable when an individual destination page blocks
    server-side fetching. This prevents Render/network restrictions from
    turning a successful search into a false `no_results` response.
    """

    SEARCH_URLS = (
        "https://html.duckduckgo.com/html/",
        "https://lite.duckduckgo.com/lite/",
    )
    TIMEOUT = httpx.Timeout(12.0, connect=8.0)
    MAX_RESULTS = 12
    MAX_PAGE_CHARS = 18000

    OFFICIAL_DOMAINS = {
        "eci.gov.in": ("official_electoral", 1.0),
        "loksabha.nic.in": ("official_parliament", 1.0),
        "sansad.in": ("official_parliament", 1.0),
        "pmindia.gov.in": ("official_government", 1.0),
        "india.gov.in": ("official_government", 1.0),
        "supremecourtofindia.nic.in": ("official_judiciary", 1.0),
        "sci.gov.in": ("official_judiciary", 1.0),
        "inc.in": ("party_official", 0.65),
        "bjp.org": ("party_official", 0.65),
    }
    NEWS_DOMAINS = {
        "reuters.com", "apnews.com", "bbc.com", "thehindu.com",
        "indianexpress.com", "economictimes.indiatimes.com", "news18.com",
    }

    def search(self, query: str) -> list[dict]:
        queries = self._build_queries(query)
        documents: list[dict] = []
        seen: set[str] = set()
        search_attempts = 0
        successful_searches = 0

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/124.0 Safari/537.36 Factygo/2.0"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        }

        with httpx.Client(
            timeout=self.TIMEOUT,
            follow_redirects=True,
            headers=headers,
        ) as client:
            for search_query in queries:
                search_attempts += 1
                results = self._search_once(client, search_query)
                if results:
                    successful_searches += 1
                for item in results:
                    url = item["url"]
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    source_type, score = self._source_profile(url)
                    documents.append({
                        "title": item["title"][:300],
                        "url": url,
                        "snippet": item["snippet"][:1500],
                        "source_score": score,
                        "source_type": source_type,
                    })
                    if len(documents) >= self.MAX_RESULTS:
                        break
                if len(documents) >= self.MAX_RESULTS:
                    break

            # Try original pages, but NEVER discard a result if page retrieval fails.
            for document in documents:
                page_text = self._fetch_page(client, document["url"])
                document["text"] = page_text or document.get("snippet", "")
                document["page_retrieved"] = bool(page_text)
                document["retrieved"] = bool(document.get("text"))

        # Preserve search-result snippets as evidence when destination fetches fail.
        for document in documents:
            document["research_status"] = (
                "page_retrieved"
                if document.get("page_retrieved")
                else "search_snippet_only"
            )
        return [d for d in documents if d.get("retrieved")]

    def normalize(self, documents: list[dict]) -> list[Source]:
        return [
            Source(
                title=doc.get("title", "Untitled"),
                url=doc.get("url", ""),
                domain=urlparse(doc.get("url", "")).netloc.removeprefix("www."),
                source_score=float(doc.get("source_score", 0)),
                source_type=doc.get("source_type", "unknown"),
                source_tier=self._tier(float(doc.get("source_score", 0))),
            )
            for doc in documents
        ]

    @staticmethod
    def _build_queries(claim: str) -> list[str]:
        clean = re.sub(r"\s+", " ", claim).strip()
        lower = clean.lower()
        queries = [clean, f'"{clean}"']
        if any(x in lower for x in (
            "congress", "bjp", "aap", "party", "ruling",
            "government", "minister", "prime minister", "president",
        )):
            queries += [
                f"{clean} India Union government",
                f"{clean} central government",
                f"{clean} Lok Sabha",
                f"{clean} official",
            ]
        else:
            queries += [f"{clean} facts", f"{clean} official"]
        return list(dict.fromkeys(queries))

    def _search_once(self, client: httpx.Client, query: str) -> list[dict]:
        # Try both DDG endpoints. Their HTML structures differ, so parse both.
        for endpoint in self.SEARCH_URLS:
            try:
                response = client.get(endpoint, params={"q": query})
                response.raise_for_status()
            except httpx.HTTPError:
                continue

            results = self._parse_search_html(response.text)
            if results:
                return results
        return []

    def _parse_search_html(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results: list[dict] = []

        # Standard DuckDuckGo HTML endpoint.
        for result in soup.select(".result"):
            link = result.select_one("a.result__a")
            if not link:
                continue
            url = self._clean_url(link.get("href", ""))
            if not url:
                continue
            snippet_node = result.select_one(".result__snippet")
            results.append({
                "title": link.get_text(" ", strip=True),
                "url": url,
                "snippet": snippet_node.get_text(" ", strip=True) if snippet_node else "",
            })

        if results:
            return results

        # DuckDuckGo Lite fallback.
        for link in soup.select("a.result-link, a.result__a"):
            url = self._clean_url(link.get("href", ""))
            if not url:
                continue
            title = link.get_text(" ", strip=True)
            parent = link.parent
            snippet = ""
            if parent:
                candidate = parent.find_next(string=lambda s: s and len(s.strip()) > 30)
                if candidate:
                    snippet = candidate.strip()
            results.append({"title": title, "url": url, "snippet": snippet})

        # Generic fallback for links if DDG changes its classes.
        if not results:
            for link in soup.find_all("a", href=True):
                url = self._clean_url(link.get("href", ""))
                title = link.get_text(" ", strip=True)
                if url and title and len(title) > 5:
                    results.append({"title": title, "url": url, "snippet": ""})
                if len(results) >= self.MAX_RESULTS:
                    break

        return results[: self.MAX_RESULTS]

    @staticmethod
    def _clean_url(raw: str) -> str:
        if raw.startswith("//"):
            raw = "https:" + raw
        parsed = urlparse(raw)
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            return unquote(parse_qs(parsed.query).get("uddg", [""])[0])
        return raw if parsed.scheme in {"http", "https"} else ""

    def _fetch_page(self, client: httpx.Client, url: str) -> str:
        try:
            response = client.get(url)
            response.raise_for_status()
            if "text/html" not in response.headers.get("content-type", ""):
                return ""
            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup([
                "script", "style", "noscript", "svg", "nav", "footer", "form"
            ]):
                tag.decompose()
            return re.sub(
                r"\s+", " ", soup.get_text(" ", strip=True)
            )[: self.MAX_PAGE_CHARS]
        except (httpx.HTTPError, UnicodeError):
            return ""

    @classmethod
    def _source_profile(cls, url: str) -> tuple[str, float]:
        domain = urlparse(url).netloc.lower().removeprefix("www.")
        if domain in cls.OFFICIAL_DOMAINS:
            return cls.OFFICIAL_DOMAINS[domain]
        if domain.endswith(".gov.in") or domain.endswith(".gov") or domain.endswith(".nic.in"):
            return "official", 0.95
        if domain.endswith(".edu") or domain.endswith(".ac.in"):
            return "academic", 0.90
        if any(domain == d or domain.endswith("." + d) for d in cls.NEWS_DOMAINS):
            return "news", 0.80
        return "web", 0.50

    @staticmethod
    def _tier(score: float) -> int:
        if score >= .95:
            return 1
        if score >= .85:
            return 2
        if score >= .75:
            return 3
        return 4
