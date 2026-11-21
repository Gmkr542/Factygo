from __future__ import annotations

import asyncio
import html
import logging
import re
from urllib.parse import parse_qsl, quote_plus, urlencode, urlparse, urlunparse
from xml.etree import ElementTree as ET

import httpx

from app.core.config import get_settings
from app.services.source_validator import source_type_for

logger = logging.getLogger(__name__)


class SearchError(Exception):
    pass


_ddgs_lock = asyncio.Lock()
_ddgs_unavailable_until = 0.0
_DDGS_COOLDOWN_SECONDS = 60.0

_RESOURCE_DOMAINS = {
    "government/official": ["gov.in", "india.gov.in", "pib.gov.in", "pmindia.gov.in", "sansad.in", "gov"],
    "election authority": ["eci.gov.in"],
    "courts/law": ["sci.gov.in", "indiacode.nic.in"],
    "academic/research": ["pubmed.ncbi.nlm.nih.gov", "nature.com", "sciencedirect.com", "arxiv.org"],
    "medical/health authorities": ["who.int", "cdc.gov", "nih.gov", "pubmed.ncbi.nlm.nih.gov", "mayoclinic.org", "healthline.com"],
    "financial/regulatory": ["rbi.org.in", "sebi.gov.in", "sec.gov", "imf.org", "worldbank.org"],
    "reputable news": ["reuters.com", "apnews.com", "bbc.com", "thehindu.com", "indianexpress.com"],
    "fact-checking": ["factcheck.org", "snopes.com", "altnews.in", "boomlive.in"],
}

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "in", "is", "it", "of", "on", "or", "that", "the", "their", "this", "to", "was",
    "were", "will", "with", "without", "against", "about", "into", "than", "then", "they",
    "them", "there", "these", "those", "what", "when", "where", "which", "who", "why", "how",
}


def _clean_text(value: str) -> str:
    unescaped = html.unescape(str(value or ""))
    return " ".join(unescaped.replace("\xa0", " ").split()).strip()


def _quality(source_type: str) -> tuple[int, str, int]:
    kind = str(source_type or "").lower()
    if kind == "government":
        return (95, "Primary/Official", 1)
    if kind in {"academic/scientific", "academic"}:
        return (92, "Academic/Scientific", 1)
    if "fact-check" in kind:
        return (88, "Fact-Checking", 2)
    if "major news" in kind:
        return (82, "Major News", 2)
    return (65, "General Web", 3)


def _canonical_url(value: str) -> str:
    try:
        parsed = urlparse(str(value).strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        host = parsed.netloc.lower().removeprefix("www.")
        tracking_names = {"gclid", "fbclid", "mc_cid", "mc_eid", "ref", "ref_src", "oc"}
        params = [
            (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if not k.lower().startswith("utm_") and k.lower() not in tracking_names
        ]
        return urlunparse((parsed.scheme.lower(), host, parsed.path.rstrip("/") or "/", "", urlencode(sorted(params)), ""))
    except Exception:
        return str(value).strip().rstrip("/")


def _normalise(results: list[dict]) -> list[dict]:
    out = []
    seen = set()
    for x in results:
        if not isinstance(x, dict):
            continue
        u = x.get("href") or x.get("url") or ""
        canonical = _canonical_url(u)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        title = _clean_text(x.get("title", ""))[:300]
        domain = str(x.get("domain") or "").strip().lower().removeprefix("www.")
        if not domain:
            domain = urlparse(u).netloc.lower().removeprefix("www.")
        publisher = _clean_text(x.get("publisher") or domain)
        st = source_type_for(title, publisher, f"https://{domain}" if domain else u)
        quality, tier_label, tier_num = _quality(st)
        raw_body = x.get("body") or x.get("description") or x.get("content") or ""
        content = _clean_text(re.sub(r"<[^>]+>", " ", str(raw_body)))[:5000]
        out.append({
            "title": title,
            "url": u,
            "domain": domain,
            "content": content,
            "text": content,
            "publisher": publisher,
            "source_type": st,
            "source_quality": quality,
            "source_score": round(quality / 100.0, 2),
            "source_tier": tier_label,
            "tier": tier_num,
        })
    return out


def _ddgs_search(query: str, max_results: int, backend: str | None = None) -> list[dict]:
    from ddgs import DDGS
    kwargs = {"max_results": max_results}
    if backend:
        kwargs["backend"] = backend
    return list(DDGS().text(query, **kwargs))


async def _ddgs(query: str, max_results: int) -> list[dict]:
    global _ddgs_unavailable_until
    async with _ddgs_lock:
        now = asyncio.get_running_loop().time()
        if now < _ddgs_unavailable_until:
            return []
        timeout = max(3.0, float(get_settings().search_timeout))
        attempts = [(None, min(timeout, 5.0)), ("google", min(timeout, 4.0)), ("bing", min(timeout, 4.0))]
        failures = []
        for backend, limit in attempts:
            try:
                raw = await asyncio.wait_for(
                    asyncio.to_thread(_ddgs_search, query, max_results, backend),
                    timeout=limit,
                )
                results = _normalise(raw)
                if results:
                    _ddgs_unavailable_until = 0.0
                    return results
            except Exception as e:
                failures.append((backend or "primary", type(e).__name__))
        if failures:
            _ddgs_unavailable_until = asyncio.get_running_loop().time() + _DDGS_COOLDOWN_SECONDS
            logger.warning("DDGS search unavailable; pausing for %ss: %s", int(_DDGS_COOLDOWN_SECONDS), failures)
        return []


async def _google_news(query: str, max_results: int) -> list[dict]:
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    try:
        async with httpx.AsyncClient(
            timeout=get_settings().search_timeout,
            follow_redirects=True,
            headers={"User-Agent": "Factygo/1.1"},
        ) as client:
            r = await client.get(url)
            r.raise_for_status()
        root = ET.fromstring(r.text)
    except Exception as e:
        logger.debug("Google News RSS failed: %s", type(e).__name__)
        return []

    results = []
    for item in root.findall(".//item")[:max_results]:
        raw_title = _clean_text(item.findtext("title") or "")
        source_el = item.find("source")
        source_name = _clean_text(source_el.text or "") if source_el is not None else ""
        source_url = source_el.attrib.get("url", "").strip() if source_el is not None else ""
        real_domain = urlparse(source_url).netloc.lower().removeprefix("www.") if source_url else ""
        if not source_name and " - " in raw_title:
            source_name = raw_title.rsplit(" - ", 1)[-1].strip()
        desc = _clean_text(re.sub(r"<[^>]+>", " ", item.findtext("description") or ""))
        results.append({
            "title": raw_title,
            "url": item.findtext("link") or source_url,
            "domain": real_domain or source_name.lower(),
            "publisher": source_name or real_domain or "News Source",
            "body": desc or raw_title,
        })
    return _normalise(results)


async def _pubmed_fallback(query: str, max_results: int = 3) -> list[dict]:
    keywords = " ".join(sorted(_terms(query)))
    if not keywords:
        return []
    try:
        async with httpx.AsyncClient(timeout=get_settings().search_timeout, headers={"User-Agent": "Factygo/1.1"}) as client:
            sr = await client.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                params={"db": "pubmed", "term": keywords, "retmode": "json", "retmax": max_results},
            )
            sr.raise_for_status()
            ids = sr.json().get("esearchresult", {}).get("idlist", [])
            if not ids:
                return []
            sm = await client.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
            )
            sm.raise_for_status()
            rmap = sm.json().get("result", {})
    except Exception:
        return []

    results = []
    for pmid in ids:
        entry = rmap.get(pmid)
        if isinstance(entry, dict) and entry.get("title"):
            title = _clean_text(entry["title"])
            src = _clean_text(entry.get("source", "PubMed"))
            results.append({
                "title": title,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "domain": "pubmed.ncbi.nlm.nih.gov",
                "publisher": src,
                "body": f"{title} Published in {src} ({entry.get('pubdate', '')}).",
            })
    return _normalise(results)


async def _wikipedia_fallback(query: str, max_results: int = 3) -> list[dict]:
    keywords = " ".join(list(_terms(query))[:6]) or query[:100]
    try:
        async with httpx.AsyncClient(timeout=get_settings().search_timeout, headers={"User-Agent": "Factygo/1.1"}) as client:
            r = await client.get(
                "https://en.wikipedia.org/w/api.php",
                params={"action": "query", "list": "search", "srsearch": keywords, "format": "json", "srlimit": max_results},
            )
            r.raise_for_status()
            hits = r.json().get("query", {}).get("search", [])
    except Exception:
        return []

    results = []
    for hit in hits:
        title = _clean_text(hit.get("title", ""))
        snippet = _clean_text(re.sub(r"<[^>]+>", " ", str(hit.get("snippet", ""))))
        if title:
            results.append({
                "title": f"{title} - Wikipedia",
                "url": f"https://en.wikipedia.org/wiki/{quote_plus(title.replace(' ', '_'))}",
                "domain": "en.wikipedia.org",
                "publisher": "Wikipedia",
                "body": snippet or title,
            })
    return _normalise(results)


def _terms(value: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", value.lower()) if t not in _STOPWORDS}


def _score_relevance(query: str, item: dict) -> int:
    q = " ".join(query.split()).lower()
    qt = _terms(q)
    hay = f"{item.get('title', '')} {item.get('publisher', '')} {item.get('content', '')}".lower()
    ht = _terms(hay)
    if not qt:
        item["relevance_score"] = 50
        item["relevant"] = True
        return 50
    overlap = qt & ht
    coverage = len(overlap) / len(qt)
    title_overlap = len(qt & _terms(str(item.get("title", ""))))
    exact = 1 if q in hay and len(q) > 10 else 0
    score = min(100, round(coverage * 65 + min(title_overlap, 3) * 8 + exact * 25))
    item["relevance_score"] = score
    item["relevance_reason"] = (
        "Exact phrase match" if exact else f"{len(overlap)}/{len(qt)} key terms match ({title_overlap} in title)"
    )
    item["relevant"] = bool(exact or (len(overlap) >= (1 if len(qt) <= 2 else 2) and score >= 45))
    return score


def _clean_search_query(query: str) -> str:
    cleaned = re.sub(
        r"^(?:what authoritative sources establish the factual status of:|"
        r"what primary or original source evidence is available for:|"
        r"what reliable evidence contradicts or limits this claim:)\s*",
        "",
        query.strip(),
        flags=re.I,
    )
    return " ".join(cleaned.split())[:220]


def _plan_queries(base_query: str, plan: dict | None) -> list[str]:
    if not plan:
        return []
    terms = [f"{base_query} {str(x).strip()}"[:240] for x in plan.get("search_strategy", [])[:3] if str(x).strip()]
    domains = []
    for d in plan.get("preferred_domains", [])[:4]:
        d = str(d).strip().lower().removeprefix("https://").removeprefix("http://").split("/")[0]
        if "." in d:
            domains.append(d)
    for rtype in plan.get("resource_types", [])[:4]:
        domains.extend(_RESOURCE_DOMAINS.get(str(rtype).lower(), []))
    domain_queries = [f"{base_query} site:{d}" for d in dict.fromkeys(domains)][:3]
    return list(dict.fromkeys(terms + domain_queries))


async def search_web(query: str, max_results: int | None = None, resource_plan: dict | None = None) -> list[dict]:
    max_results = max(2, min(max_results or get_settings().max_search_results, 25))
    base_q = _clean_search_query(query)
    queries = [base_q] + _plan_queries(base_q, resource_plan)
    provider_queries = list(dict.fromkeys(queries))[:3]

    ddgs_task = asyncio.gather(*[_ddgs(q, min(max_results, 8)) for q in provider_queries[:2]], return_exceptions=True)
    news_task = asyncio.gather(*[_google_news(q, min(max_results, 8)) for q in provider_queries[:2]], return_exceptions=True)
    pubmed_task = _pubmed_fallback(base_q, max_results=3)
    ddgs_batches, news_batches, pubmed_results = await asyncio.gather(ddgs_task, news_task, pubmed_task)

    combined = []
    for batch in list(ddgs_batches) + list(news_batches):
        if isinstance(batch, list):
            combined.extend(batch)
    if isinstance(pubmed_results, list):
        combined.extend(pubmed_results)
    if len(combined) < 3:
        combined.extend(await _wikipedia_fallback(base_q, max_results=3))

    results = _normalise(combined)
    for item in results:
        _score_relevance(base_q, item)

    ranked = sorted(
        results,
        key=lambda x: (x.get("relevance_score", 0), x.get("source_quality", 0), len(x.get("content", ""))),
        reverse=True,
    )
    out = []
    seen_urls = set()
    seen_publishers = set()
    for item in ranked:
        if item["url"] in seen_urls:
            continue
        pub = (item.get("domain") or item["publisher"]).lower()
        if pub in seen_publishers and item["source_quality"] < 90:
            continue
        out.append(item)
        seen_urls.add(item["url"])
        seen_publishers.add(pub)
        if len(out) >= min(max_results, 15):
            break
    return out


class ResearchService:
    """Compatibility wrapper matching FactyGo's original ResearchService interface."""

    def search(self, query: str) -> list[dict]:
        return asyncio.run(search_web(query))

    async def asearch(self, query: str, resource_plan: dict | None = None) -> list[dict]:
        return await search_web(query, resource_plan=resource_plan)

    def normalize(self, documents: list[dict]) -> list[dict]:
        seen = set()
        normalized = []
        for doc in documents:
            url = doc.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            normalized.append({
                "title": doc.get("title", "Untitled"),
                "url": url,
                "domain": doc.get("domain", ""),
                "publisher": doc.get("publisher", ""),
                "source_type": doc.get("source_type", "Web Source"),
                "source_quality": doc.get("source_quality", 65),
                "source_tier": doc.get("source_tier", "General Web"),
                "relevance_score": doc.get("relevance_score", 0),
            })
        return normalized
