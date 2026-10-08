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


## Input policy
Attachments are optional. Text-only investigation is a first-class flow; image/PDF/DOCX uploads are separate optional capabilities. The investigation API must not require a document attachment.

## V8 Question-Decomposition Pipeline

The investigation flow is now:

`Original input -> framed questions -> independent research per question -> raw source-grounded answers -> combined evidence -> validation/cross-check -> final synthesis for the original input.`

Framed questions are research tasks, not independent verdicts. Search snippets remain discovery-only; retrieved source-page content is the evidence corpus. The final verdict is evaluated against the original investigation input after all question research is combined.
