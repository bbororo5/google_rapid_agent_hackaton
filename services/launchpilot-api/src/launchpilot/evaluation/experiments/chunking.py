from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Sequence
from typing import Protocol

from .contracts import Chunk, ChunkingConfig, ChunkingMethod, EvaluationDocument

_TOKEN_PATTERN = re.compile(r"\S+")
_SENTENCE_PATTERN = re.compile(r".+?(?:[.!?。！？](?:\s+|$)|\n+|$)", re.DOTALL)


class DocumentChunker(Protocol):
    @property
    def config(self) -> ChunkingConfig: ...

    def chunk(self, document: EvaluationDocument) -> tuple[Chunk, ...]: ...


class SemanticEncoder(Protocol):
    def encode_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class ConfiguredChunker:
    def __init__(
        self,
        config: ChunkingConfig,
        *,
        semantic_encoder: SemanticEncoder | None = None,
    ) -> None:
        self._config = config
        self._semantic_encoder = semantic_encoder

    @property
    def config(self) -> ChunkingConfig:
        return self._config

    def chunk(self, document: EvaluationDocument) -> tuple[Chunk, ...]:
        method = self._config.method
        if method == ChunkingMethod.WHOLE_DOCUMENT:
            spans = [(0, len(document.text))]
        elif method == ChunkingMethod.FIXED_TOKEN:
            spans = _fixed_token_spans(
                document.text,
                max_tokens=self._config.max_tokens,
                overlap_tokens=self._config.overlap_tokens,
            )
        elif method == ChunkingMethod.SENTENCE:
            spans = _packed_sentence_spans(
                document.text,
                max_tokens=self._config.max_tokens,
                overlap_tokens=self._config.overlap_tokens,
            )
        elif method == ChunkingMethod.RECURSIVE:
            spans = _recursive_spans(
                document.text,
                max_tokens=self._config.max_tokens,
                overlap_tokens=self._config.overlap_tokens,
            )
        elif method == ChunkingMethod.SEMANTIC:
            if self._semantic_encoder is None:
                raise RuntimeError(
                    "semantic chunking requires an embedding-aware chunker adapter"
                )
            spans = _semantic_spans(
                document.text,
                max_tokens=self._config.max_tokens,
                overlap_tokens=self._config.overlap_tokens,
                encoder=self._semantic_encoder,
            )
        else:
            raise ValueError(f"unsupported chunking method: {method}")
        return tuple(
            _chunk(document, self._config, index, start, end)
            for index, (start, end) in enumerate(_deduplicate_spans(spans))
            if document.text[start:end].strip()
        )


def chunk_documents(
    documents: Sequence[EvaluationDocument],
    config: ChunkingConfig,
    *,
    semantic_encoder: SemanticEncoder | None = None,
) -> tuple[Chunk, ...]:
    chunker = ConfiguredChunker(config, semantic_encoder=semantic_encoder)
    return tuple(chunk for document in documents for chunk in chunker.chunk(document))


def _fixed_token_spans(
    text: str, *, max_tokens: int, overlap_tokens: int
) -> list[tuple[int, int]]:
    tokens = list(_TOKEN_PATTERN.finditer(text))
    if not tokens:
        return []
    step = max_tokens - overlap_tokens
    spans = []
    for offset in range(0, len(tokens), step):
        window = tokens[offset : offset + max_tokens]
        if not window:
            break
        spans.append((window[0].start(), window[-1].end()))
        if offset + max_tokens >= len(tokens):
            break
    return spans


def _packed_sentence_spans(
    text: str, *, max_tokens: int, overlap_tokens: int
) -> list[tuple[int, int]]:
    sentences = [
        item for item in _SENTENCE_PATTERN.finditer(text) if item.group().strip()
    ]
    if not sentences:
        return _fixed_token_spans(
            text, max_tokens=max_tokens, overlap_tokens=overlap_tokens
        )
    spans: list[tuple[int, int]] = []
    start_index = 0
    while start_index < len(sentences):
        first_sentence = sentences[start_index]
        first_token_count = len(_TOKEN_PATTERN.findall(first_sentence.group()))
        if first_token_count > max_tokens:
            spans.extend(
                (
                    first_sentence.start() + left,
                    first_sentence.start() + right,
                )
                for left, right in _fixed_token_spans(
                    first_sentence.group(),
                    max_tokens=max_tokens,
                    overlap_tokens=overlap_tokens,
                )
            )
            start_index += 1
            continue
        end_index = start_index
        token_count = 0
        while end_index < len(sentences):
            sentence_tokens = len(_TOKEN_PATTERN.findall(sentences[end_index].group()))
            if end_index > start_index and token_count + sentence_tokens > max_tokens:
                break
            token_count += sentence_tokens
            end_index += 1
        if end_index > start_index:
            spans.append(
                (sentences[start_index].start(), sentences[end_index - 1].end())
            )
        if end_index >= len(sentences):
            break
        overlap_count = 0
        next_start = end_index
        while next_start > start_index and overlap_count < overlap_tokens:
            next_start -= 1
            overlap_count += len(_TOKEN_PATTERN.findall(sentences[next_start].group()))
        start_index = max(start_index + 1, next_start)
    return spans


def _recursive_spans(
    text: str, *, max_tokens: int, overlap_tokens: int
) -> list[tuple[int, int]]:
    blocks = [
        match
        for match in re.finditer(
            r"(?:^|\n)(?:#{1,6}\s+[^\n]+\n)?[^\n]+(?:\n(?!\n)[^\n]+)*", text
        )
        if match.group().strip()
    ]
    if not blocks:
        return _packed_sentence_spans(
            text, max_tokens=max_tokens, overlap_tokens=overlap_tokens
        )
    spans: list[tuple[int, int]] = []
    for block in blocks:
        count = len(_TOKEN_PATTERN.findall(block.group()))
        if count <= max_tokens:
            spans.append((block.start(), block.end()))
            continue
        for left, right in _packed_sentence_spans(
            block.group(),
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        ):
            spans.append((block.start() + left, block.start() + right))
    return spans


def _semantic_spans(
    text: str,
    *,
    max_tokens: int,
    overlap_tokens: int,
    encoder: SemanticEncoder,
) -> list[tuple[int, int]]:
    sentences = [
        item for item in _SENTENCE_PATTERN.finditer(text) if item.group().strip()
    ]
    if len(sentences) < 2:
        return _fixed_token_spans(
            text, max_tokens=max_tokens, overlap_tokens=overlap_tokens
        )
    if any(
        len(_TOKEN_PATTERN.findall(sentence.group())) > max_tokens
        for sentence in sentences
    ):
        return _packed_sentence_spans(
            text, max_tokens=max_tokens, overlap_tokens=overlap_tokens
        )
    sentence_texts = [sentence.group().strip() for sentence in sentences]
    vectors = encoder.encode_documents(sentence_texts)
    if len(vectors) != len(sentences):
        raise ValueError("semantic encoder returned the wrong number of vectors")
    similarities = [
        _cosine(vectors[index], vectors[index + 1]) for index in range(len(vectors) - 1)
    ]
    ordered = sorted(similarities)
    breakpoint = ordered[max(int(len(ordered) * 0.25) - 1, 0)]
    token_counts = [len(_TOKEN_PATTERN.findall(item)) for item in sentence_texts]
    minimum_tokens = max(16, int(max_tokens * 0.35))
    spans: list[tuple[int, int]] = []
    start_index = 0
    while start_index < len(sentences):
        end_index = start_index
        token_count = 0
        while end_index < len(sentences):
            next_count = token_counts[end_index]
            if end_index > start_index and token_count + next_count > max_tokens:
                break
            token_count += next_count
            end_index += 1
            boundary_index = end_index - 1
            if (
                end_index < len(sentences)
                and token_count >= minimum_tokens
                and similarities[boundary_index] <= breakpoint
            ):
                break
        if end_index == start_index:
            return _fixed_token_spans(
                text, max_tokens=max_tokens, overlap_tokens=overlap_tokens
            )
        spans.append((sentences[start_index].start(), sentences[end_index - 1].end()))
        if end_index >= len(sentences):
            break
        overlap_count = 0
        next_start = end_index
        while next_start > start_index + 1 and overlap_count < overlap_tokens:
            next_start -= 1
            overlap_count += token_counts[next_start]
        start_index = max(start_index + 1, next_start)
    return spans


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("semantic vectors must have the same dimensions")
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = sum(value * value for value in left) ** 0.5
    right_norm = sum(value * value for value in right) ** 0.5
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _chunk(
    document: EvaluationDocument,
    config: ChunkingConfig,
    index: int,
    start: int,
    end: int,
) -> Chunk:
    identity = f"{document.document_ref}|{config.version}|{index}|{start}|{end}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return Chunk(
        chunk_id=f"chunk:{digest}",
        document_ref=document.document_ref,
        text=document.text[start:end].strip(),
        char_start=start,
        char_end=end,
        metadata={
            **document.metadata,
            "title": document.title,
            "campaign_ref": document.campaign_ref,
        },
    )


def _deduplicate_spans(spans: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    return list(dict.fromkeys(spans))
