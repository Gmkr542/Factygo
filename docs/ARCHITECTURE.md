# Factygo Architecture

## Evidence-first pipeline

Input
→ claim extraction
→ claim decomposition
→ research
→ source normalization/ranking
→ evidence extraction
→ supporting/contradicting/context classification
→ contradiction analysis
→ verdict
→ confidence
→ citation-backed report

## Engineering principles

1. Evidence before verdict.
2. No fabricated sources.
3. Provider abstraction.
4. Small replaceable services.
5. Database persistence separated from API.
6. Expensive work can move to background workers.
7. Local/free AI is supported.
8. Every AI result should be evaluated.

## Target architecture

Next.js
→ FastAPI
→ PostgreSQL

FastAPI
→ Research providers
→ AI provider
→ Vector retrieval
→ Background jobs

Later:
Redis → Worker → Research/OCR/RAG
