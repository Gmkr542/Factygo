# Factygo Intelligence v3

## Goal
Prevent scope errors such as treating a state government as evidence that a party controls India's Union government.

## Pipeline
1. Claim normalization: subject, claim type, jurisdiction, year.
2. Claim-aware search expansion.
3. Source authority profiling and tiers.
4. Sentence-level evidence extraction.
5. Jurisdiction and temporal matching.
6. Supporting / contradicting / contextual stance classification.
7. Independent-domain corroboration.
8. Evidence-weighted verdict and confidence.

## Jurisdiction
- UNION: Centre, Center, central government, Union government, Government of India, Lok Sabha.
- STATE: state governments and state-specific political evidence.

State-level evidence is not allowed to support a Union-government claim unless the passage also contains Union-level scope.

## Important limitation
This is a deterministic intelligence layer, not a statistical semantic-entailment model. It is designed to be conservative and provider-neutral at ₹0. A future local/open model can replace or augment the rule-based stance evaluator without changing the API contract.
