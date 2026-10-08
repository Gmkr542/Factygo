from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from app.schemas.investigation import Source


class ResearchService:
    """Fast, resilient evidence-first web research.

    Search results are discovery records only. A destination page must be
    successfully retrieved before its text can enter the evidence pipeline.
    This prevents truncated/stale search snippets from being treated as proof.
    """

    SEARCH_URLS = (
        "https://html.duckduckgo.com/html/",
        "https://lite.duckduckgo.com/lite/",
    )
    SEARCH_TIMEOUT = httpx.Timeout(5.0, connect=3.0)
    PAGE_TIMEOUT = httpx.Timeout(3.5, connect=2.0)
    MAX_RESULTS = 10
    MAX_PAGE_FETCHES = 5
    MAX_PAGE_CHARS = 16000

    OFFICIAL_DOMAINS = {
        "eci.gov.in": ("official_electoral", 1.0),
        "loksabha.nic.in": ("official_parliament", 1.0),
        "sansad.in": ("official_parliament", 1.0),
        "pmindia.gov.in": ("official_government", 1.0),
        "india.gov.in": ("official_government", 1.0),
        "sci.gov.in": ("official_judiciary", 1.0),
        "supremecourtofindia.nic.in": ("official_judiciary", 1.0),
        "inc.in": ("party_official", 0.65),
        "bjp.org": ("party_official", 0.65),
    }
    NEWS_DOMAINS = {
        "reuters.com", "apnews.com", "bbc.com", "thehindu.com",
        "indianexpress.com", "economictimes.indiatimes.com", "news18.com",
        "ndtv.com", "hindustantimes.com", "timesofindia.indiatimes.com",
    }

    def search(self, query: str) -> list[dict]:
        queries = self._build_queries(query)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/124.0 Safari/537.36 Factygo/2.0"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        }

        # Search in parallel. A blocked provider/query no longer serially stalls
        # the whole investigation.
        found: list[dict] = []
        seen: set[str] = set()

        def run_search(q: str) -> list[dict]:
            with httpx.Client(
                timeout=self.SEARCH_TIMEOUT,
                follow_redirects=True,
                headers=headers,
            ) as client:
                return self._search_once(client, q)

        with ThreadPoolExecutor(max_workers=min(3, len(queries))) as pool:
            futures = [pool.submit(run_search, q) for q in queries]
            for future in as_completed(futures):
                try:
                    results = future.result()
                except Exception:
                    results = []
                for item in results:
                    url = item.get("url", "")
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    source_type, score = self._source_profile(url)
                    found.append({
                        "title": item.get("title", "Untitled")[:300],
                        "url": url,
                        "snippet": item.get("snippet", "")[:1800],
                        "source_score": score,
                        "source_type": source_type,
                        # Search snippets are discovery metadata, never evidence.
                        "text": "",
                        "page_retrieved": False,
                        "research_status": "search_result_only",
                    })
                    if len(found) >= self.MAX_RESULTS:
                        break
                if len(found) >= self.MAX_RESULTS:
                    break

        if not found:
            return []

        # Enrich only the top few pages. Snippet-only results are retained as
        # discovery metadata but are excluded from the returned evidence corpus.
        candidates = found[: self.MAX_PAGE_FETCHES]

        def fetch_one(document: dict) -> tuple[str, str]:
            try:
                with httpx.Client(
                    timeout=self.PAGE_TIMEOUT,
                    follow_redirects=True,
                    headers=headers,
                ) as client:
                    return document["url"], self._fetch_page(client, document["url"])
            except Exception:
                return document["url"], ""

        with ThreadPoolExecutor(max_workers=min(5, len(candidates))) as pool:
            futures = [pool.submit(fetch_one, d) for d in candidates]
            for future in as_completed(futures):
                try:
                    url, page_text = future.result()
                except Exception:
                    continue
                for document in found:
                    if document["url"] == url and page_text:
                        document["text"] = page_text
                        document["page_retrieved"] = True
                        document["research_status"] = "page_retrieved"
                        break

        # Only successfully retrieved source content is evidence-bearing.
        return [d for d in found if d.get("page_retrieved") and d.get("text")]

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
        # Keep the query set small: one exact/general search + one domain-aware
        # search. More queries add latency without proportional evidence gain.
        if any(x in lower for x in (
            "congress", "bjp", "aap", "party", "ruling", "government",
            "minister", "prime minister", "president", "election",
        )):
            queries = [
                clean,
                f"{clean} India Union government official",
                f"{clean} Lok Sabha current government",
            ]
            # Current political-power claims benefit from source-directed
            # discovery. These are still only discovery queries; page content
            # must be retrieved before it becomes evidence.
            if any(x in lower for x in ("congress", "bjp", "ruling", "central government", "union government")):
                queries.extend([
                    "current Prime Minister of India 2026 site:pmindia.gov.in",
                    "2024 Lok Sabha election results site:eci.gov.in",
                    "Union Government India current 2026 site:india.gov.in",
                ])
            return list(dict.fromkeys(queries))[:6]
        return [clean, f"{clean} official", f"{clean} facts"]

    def _search_once(self, client: httpx.Client, query: str) -> list[dict]:
        for endpoint in self.SEARCH_URLS:
            try:
                response = client.get(endpoint, params={"q": query})
                response.raise_for_status()
                results = self._parse_search_html(response.text)
                if results:
                    return results
            except (httpx.HTTPError, UnicodeError):
                continue
        return []

    def _parse_search_html(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results: list[dict] = []

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
            return results[: self.MAX_RESULTS]

        for link in soup.select("a.result-link, a.result__a"):
            url = self._clean_url(link.get("href", ""))
            title = link.get_text(" ", strip=True)
            if url and title:
                results.append({"title": title, "url": url, "snippet": ""})
        if results:
            return results[: self.MAX_RESULTS]

        # Last-resort generic parser for minor DDG HTML changes.
        for link in soup.find_all("a", href=True):
            url = self._clean_url(link.get("href", ""))
            title = link.get_text(" ", strip=True)
            if url and title and len(title) > 5:
                results.append({"title": title, "url": url, "snippet": ""})
            if len(results) >= self.MAX_RESULTS:
                break
        return results

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
            for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "form"]):
                tag.decompose()
            return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))[: self.MAX_PAGE_CHARS]
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
