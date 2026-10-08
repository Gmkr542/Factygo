# Factygo Architecture

## Core pipeline

Input
→ claim extraction
→ claim decomposition
→ research
→ source ranking
→ evidence extraction
→ stance classification
→ contradiction analysis
→ verdict
→ confidence
→ report

## Design principle

**Evidence before verdict.**

If the system has no evidence, it must return `UNVERIFIED` rather than hallucinating a conclusion.

## Future modules

### Research
Search engines, direct URL fetching, source normalization and ranking.

### Evidence
Relevant passage extraction and source-to-claim mapping.

### AI
LLM-based claim classification, decomposition and reasoning.

### Multimodal
Tesseract OCR, PDF/DOCX extraction and image analysis.

### Storage
PostgreSQL for users, investigations, claims, sources, evidence and history.

### Retrieval
Embeddings + vector search for semantic evidence retrieval.

### Agents
Planner, researcher, evidence analyst and report generator.

### Production
Authentication, authorization, rate limiting, caching, async workers, logging, monitoring and evaluation.
