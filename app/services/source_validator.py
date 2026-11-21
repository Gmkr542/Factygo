from urllib.parse import urlparse


def source_type_for(title: str, publisher: str, url: str) -> str:
    host = urlparse(url or "").netloc.lower().removeprefix("www.")
    pub = (publisher or "").lower()

    if host.endswith((".gov", ".gov.in", ".nic.in", ".mil", ".europa.eu")) or any(
        d in host for d in ("who.int", "cdc.gov", "nih.gov", "pib.gov.in", "pmindia.gov.in", "eci.gov.in", "sansad.in", "rbi.org.in")
    ):
        return "Government"
    if host.endswith(".edu") or any(
        d in host for d in ("pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "nature.com", "sciencedirect.com", "arxiv.org", "thelancet.com", "nejm.org", "bmj.com", "jamanetwork.com", "cochranelibrary.com")
    ):
        return "Academic/Scientific"
    if any(
        d in host for d in ("factcheck.org", "snopes.com", "politifact.com", "altnews.in", "boomlive.in", "vishvasnews.com", "factly.in", "fullfact.org", "afp.com")
    ):
        return "Fact-Check"
    if any(
        d in host or d in pub for d in ("reuters", "apnews", "associated press", "bbc", "thehindu", "indianexpress", "nytimes", "theguardian", "washingtonpost", "npr.org", "pbs.org", "bloomberg", "ft.com")
    ):
        return "Major News"
    return "Web Source"
