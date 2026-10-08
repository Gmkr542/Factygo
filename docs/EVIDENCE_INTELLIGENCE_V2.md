# Evidence Intelligence v2

Factygo v2 moves beyond returning raw search excerpts.

## Pipeline

Claim → research → source ranking → relevant evidence → stance assessment → source/domain corroboration → weighted verdict → confidence → report.

## Evidence stance

Each excerpt is classified as:
- `supporting`
- `contradicting`
- `contextual`

The current implementation is deterministic and transparent. It uses relevance, explicit language cues, source quality and independent domains. It does **not** claim that keyword matching is full semantic entailment.

## Source tiers

1. Official / government / major public institutions
2. Academic / university
3. Reputable news
4. General web

Search results are discovery. Source quality is considered separately when evidence is weighted.

## Verdicts

The engine can produce:
`TRUE`, `MOSTLY_TRUE`, `PARTLY_TRUE`, `MISLEADING`, `MOSTLY_FALSE`, `FALSE`, `UNVERIFIED`, `INSUFFICIENT_EVIDENCE`.

A claim with only contextual material remains `INSUFFICIENT_EVIDENCE`.
A claim with no retrieved material remains `UNVERIFIED`.

## Corroboration

Multiple excerpts from one domain do not count as independent confirmation. Independent domains increase evidence weight, while opposing evidence reduces confidence.

## Next intelligence upgrade

The service boundary is ready for a local/free entailment model (for example an Ollama/open-source model) without changing the public investigation API. That model can replace the deterministic stance scorer while retaining source ranking, corroboration and verdict safeguards.
