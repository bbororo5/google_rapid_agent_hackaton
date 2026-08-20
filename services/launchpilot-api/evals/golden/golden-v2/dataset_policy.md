# Marketing Golden Dataset Policy

## Scope

`golden-v1` is a method-independent evaluation collection. Retriever, chunker,
fusion, and reranker settings belong to experiment manifests, not this dataset.

## Source authority

- Exact campaign entities, periods, platforms, and metrics use PostgreSQL.
- Document meaning, diagnosis, and recommendations require authoritative documents.
- Synthetic BRIEF, MEMO, and ANALYSIS fixtures are frozen with stable source refs.

## Evidence and labels

- Positive cases point to stable PG or document corpus references and graded qrels.
- No-answer, ambiguity, and causal-overclaim cases remain `needs_review` until a human
  confirms the label.
- Document cases use `document_ref`, `char_start`, and `char_end`, never chunk IDs.

## Taxonomy

- Every case must use all required dimensions from `taxonomy_snapshot.yaml`.
- Stable codes are used for analysis; Korean and English preferred labels are display
  metadata.
- Taxonomy validity and taxonomy coverage readiness are separate gates. A valid but
  unbalanced collection must not be used as production model-selection evidence.

## Splits

Cases are deterministically assigned to tune 60%, validation 20%, and blind holdout
20%. Connected campaign evidence groups must not occur in more than one split.

## Metrics

Use routing Macro F1, retrieval Recall@K/MRR/nDCG, answer correctness and groundedness,
no-answer F1, p95 latency, and cost. Do not select a system by Accuracy alone.
