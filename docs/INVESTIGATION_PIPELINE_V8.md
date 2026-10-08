# Factygo V8 Investigation Pipeline

## Core contract

Framed questions break the investigation into independently researchable components. Each question is researched separately and produces a raw, source-grounded research answer. Those answers are evidence inputs, not final answers.

```text
Investigation input
  -> Claim understanding
  -> Question framing
  -> Q1 research -> raw answer
  -> Q2 research -> raw answer
  -> Q3 research -> raw answer
  -> ...
  -> Combine retrieved evidence
  -> Validate source quality / scope / time
  -> Cross-check and contradiction analysis
  -> Synthesize against ORIGINAL input
  -> Final verdict + confidence + citations + limitations
```

## Non-negotiable behavior

- Never treat a framed question's answer as the final verdict by itself.
- Never use search-result snippets as evidence.
- Never invent a raw answer when no source page was retrieved.
- Final synthesis must reference the original investigation input.
- A contradiction in one question can change the final verdict.
- Independent questions may return no results without invalidating other questions.
