# Factygo Research Engine v1

## Flow
Claim → DuckDuckGo search → URL normalization → page retrieval → text extraction → evidence extraction → conservative verdict.

## Cost
₹0: uses DuckDuckGo HTML search and direct HTTP retrieval. No paid API key is required.

## Safety
- Never fabricates source URLs or excerpts.
- Verdict engine does not equate keyword overlap with truth.
- Failed/unreadable pages are discarded.
- Evidence remains citation-linked to its source URL.

## Next upgrade
Replace the conservative verdict layer with semantic evidence evaluation + source-quality calibration, then add caching/background jobs.
