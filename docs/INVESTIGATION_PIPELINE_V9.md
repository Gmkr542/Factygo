# Factygo Investigation Pipeline v9

## Contract

The original investigation input is never replaced by the framed questions.

```text
Original input
  -> claim understanding
  -> investigation questions
  -> independent web research per question
  -> source-grounded raw answer per question
  -> combined evidence pool
  -> validation / scope / time / contradiction checks
  -> synthesis against the ORIGINAL input
  -> final verdict + confidence + citations + limitations
```

### Question layer
Each framed question is an independently researchable component. Its `raw_answer` is built only from successfully retrieved source-page text. Search snippets are discovery metadata and are never used as evidence.

### Final layer
The final verdict is computed from the complete evidence pool produced by all question investigations. The question answers are not themselves treated as verdicts.

### Failure behavior
If a question has no successfully retrieved source page, its raw answer explicitly reports that retrieval failed. The system does not manufacture an answer. If the evidence pool cannot establish the original claim, the final result remains `UNVERIFIED`/insufficient rather than guessing.

### High-priority political fallback
For current Indian political/government questions, deterministic primary-source seeds are added for PMO, ECI and Parliament when search providers fail. These pages still must be successfully retrieved before becoming evidence.
