from __future__ import annotations

import asyncio
import re
from urllib.parse import quote, unquote, urlparse
import httpx

WIKI_UA = "FactygoBot/3.0 (https://github.com/Gmkr542/Factygo; contact@factygo.app)"


class CitationAuditor:
    """Audits AI-generated text for hallucinated DOIs, PubMed IDs, arXiv IDs, and broken URLs."""

    DOI_RE = re.compile(r"\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)\b")
    PMID_RE = re.compile(r"\bPMID\s*[:#]?\s*(\d{6,9})\b", flags=re.I)
    ARXIV_RE = re.compile(r"\barXiv\s*[:#]?\s*(\d{4}\.\d{4,5})\b", flags=re.I)
    URL_RE = re.compile(r'https?://[^\s\)\]>"\']+')

    @classmethod
    def detect_citations(cls, text: str) -> dict:
        dois = list(dict.fromkeys(m.rstrip(".,;)") for m in cls.DOI_RE.findall(text)))[:4]
        pmids = list(dict.fromkeys(cls.PMID_RE.findall(text)))[:4]
        arxivs = list(dict.fromkeys(cls.ARXIV_RE.findall(text)))[:4]
        urls = list(dict.fromkeys(m.rstrip(".,;)") for m in cls.URL_RE.findall(text)))[:4]
        return {"dois": dois, "pmids": pmids, "arxivs": arxivs, "urls": urls}

    @classmethod
    async def audit_text(cls, text: str) -> list[dict]:
        found = cls.detect_citations(text)
        tasks = []
        for doi in found["dois"]:
            tasks.append(cls._verify_doi(doi))
        for pmid in found["pmids"]:
            tasks.append(cls._verify_pmid(pmid))
        for aid in found["arxivs"]:
            tasks.append(cls._verify_arxiv(aid))
        for url in found["urls"]:
            if "doi.org/" in url or "pubmed.ncbi.nlm.nih.gov/" in url or "arxiv.org/" in url:
                continue
            tasks.append(cls._verify_url(url))

        if not tasks:
            return []
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if isinstance(r, dict)]

    @staticmethod
    async def _verify_doi(doi: str) -> dict:
        url = f"https://api.crossref.org/works/{doi}"
        try:
            async with httpx.AsyncClient(timeout=6.0, headers={"User-Agent": WIKI_UA}) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    msg = r.json().get("message", {})
                    titles = msg.get("title") or []
                    title = str(titles[0] if titles else doi)
                    authors = msg.get("author") or []
                    first_author = authors[0].get("family", "") if authors else ""
                    year = ""
                    issued = msg.get("issued", {}).get("date-parts")
                    if issued and issued[0]:
                        year = str(issued[0][0])
                    abstract = re.sub(r"<[^>]+>", " ", str(msg.get("abstract") or "")).strip()
                    snippet = f"{title} ({year}). {abstract}".strip()
                    return {
                        "identifier": f"DOI:{doi}",
                        "status": "VERIFIED",
                        "title": title[:200],
                        "detail": f"Confirmed in CrossRef{f' ({year})' if year else ''}{f' · Lead author: {first_author}' if first_author else ''}.",
                        "url": f"https://doi.org/{doi}",
                        "domain": "doi.org",
                        "abstract": snippet[:1400],
                    }
                return {
                    "identifier": f"DOI:{doi}",
                    "status": "HALLUCINATED",
                    "title": "Unregistered DOI",
                    "detail": f"CrossRef returned HTTP {r.status_code}; this DOI does not exist.",
                    "url": "",
                }
        except Exception:
            return {
                "identifier": f"DOI:{doi}",
                "status": "UNREACHABLE",
                "title": "CrossRef lookup timed out",
                "detail": "Could not reach CrossRef API during verification.",
                "url": f"https://doi.org/{doi}",
            }

    @staticmethod
    async def _verify_pmid(pmid: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=6.0, headers={"User-Agent": WIKI_UA}) as client:
                r = await client.get(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                    params={"db": "pubmed", "id": pmid, "retmode": "json"},
                )
                entry = r.json().get("result", {}).get(pmid, {})
                if isinstance(entry, dict) and entry.get("title"):
                    title = str(entry["title"])
                    journal = str(entry.get("source", "Journal"))
                    pubdate = str(entry.get("pubdate", ""))
                    return {
                        "identifier": f"PMID:{pmid}",
                        "status": "VERIFIED",
                        "title": title[:200],
                        "detail": f"Confirmed on NCBI PubMed ({journal}, {pubdate}).",
                        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                        "domain": "pubmed.ncbi.nlm.nih.gov",
                        "abstract": f"{title} Published in {journal} ({pubdate}).",
                    }
                return {
                    "identifier": f"PMID:{pmid}",
                    "status": "HALLUCINATED",
                    "title": "Non-existent PubMed ID",
                    "detail": "No record exists on NCBI PubMed for this PMID.",
                    "url": "",
                }
        except Exception:
            return {
                "identifier": f"PMID:{pmid}",
                "status": "UNREACHABLE",
                "title": "PubMed lookup timed out",
                "detail": "Could not reach NCBI E-utilities.",
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            }

    @staticmethod
    async def _verify_arxiv(arxiv_id: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=6.0, headers={"User-Agent": WIKI_UA}) as client:
                r = await client.get(f"https://export.arxiv.org/api/query?id_list={arxiv_id}")
                if r.status_code == 200 and "<entry>" in r.text and "<title>" in r.text:
                    m_title = re.search(r"<entry>.*?<title>(.*?)</title>", r.text, flags=re.S)
                    m_sum = re.search(r"<entry>.*?<summary>(.*?)</summary>", r.text, flags=re.S)
                    m_pub = re.search(r"<entry>.*?<published>(\d{4})", r.text, flags=re.S)
                    title = " ".join((m_title.group(1) if m_title else arxiv_id).split())
                    summary = " ".join((m_sum.group(1) if m_sum else "").split())
                    pub_year = m_pub.group(1) if m_pub else ""
                    if title and "Error" not in title:
                        return {
                            "identifier": f"arXiv:{arxiv_id}",
                            "status": "VERIFIED",
                            "title": title[:200],
                            "detail": f"Confirmed in arXiv preprint repository{f' ({pub_year})' if pub_year else ''}.",
                            "url": f"https://arxiv.org/abs/{arxiv_id}",
                            "domain": "arxiv.org",
                            "abstract": f"{title} ({pub_year}). {summary}"[:1400],
                        }
                return {
                    "identifier": f"arXiv:{arxiv_id}",
                    "status": "HALLUCINATED",
                    "title": "Non-existent arXiv ID",
                    "detail": "No paper matches this arXiv identifier.",
                    "url": "",
                }
        except Exception:
            return {
                "identifier": f"arXiv:{arxiv_id}",
                "status": "UNREACHABLE",
                "title": "arXiv lookup timed out",
                "detail": "Could not reach arXiv API.",
                "url": f"https://arxiv.org/abs/{arxiv_id}",
            }

    @staticmethod
    async def _verify_url(url: str) -> dict:
        p = urlparse(url)
        host = (p.hostname or "").lower()
        try:
            async with httpx.AsyncClient(timeout=6.0, follow_redirects=True, headers={"User-Agent": WIKI_UA}) as client:
                if host.endswith("wikipedia.org") and "/wiki/" in p.path:
                    slug = unquote(p.path.split("/wiki/", 1)[1]).strip()
                    api_url = f"https://{host}/api/rest_v1/page/summary/{quote(slug, safe='')}"
                    r = await client.get(api_url)
                    if r.status_code == 200:
                        data = r.json()
                        title = str(data.get("title") or slug.replace("_", " "))
                        extract = str(data.get("extract") or "").strip()
                        return {
                            "identifier": url[:60],
                            "status": "VERIFIED",
                            "title": f"{title} — Wikipedia",
                            "detail": "Confirmed live Wikipedia article via Wikimedia REST API.",
                            "url": url,
                            "domain": host,
                            "abstract": extract[:1400],
                        }

                r = await client.head(url)
                if r.status_code >= 400:
                    r = await client.get(url)
                if r.status_code < 400:
                    return {
                        "identifier": url[:60],
                        "status": "VERIFIED",
                        "title": "Live URL Reachable",
                        "detail": f"Responded with HTTP {r.status_code}.",
                        "url": str(r.url),
                        "domain": host,
                    }
                return {
                    "identifier": url[:60],
                    "status": "BROKEN_LINK",
                    "title": f"HTTP {r.status_code} Error",
                    "detail": "The cited link returned an error or does not exist.",
                    "url": url,
                }
        except Exception:
            return {
                "identifier": url[:60],
                "status": "BROKEN_LINK",
                "title": "Unreachable URL",
                "detail": "Connection failed or domain does not resolve.",
                "url": url,
            }
