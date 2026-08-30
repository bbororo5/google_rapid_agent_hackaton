from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from launchpilot.evaluation.task_dataset import WorldManifest, verify_world_artifacts


class ResolvedEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_ref: str = Field(min_length=1)
    artifact_role: str = Field(min_length=1)
    title: str | None = None
    content: str = Field(min_length=1)
    record_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class EvidenceResolution(BaseModel):
    """Canonical records plus refs the system emitted but the world cannot resolve."""

    model_config = ConfigDict(frozen=True)

    resolved: tuple[ResolvedEvidence, ...]
    unknown_refs: tuple[str, ...] = ()


class WorldEvidenceResolver:
    """Resolve evidence refs against immutable canonical world artifacts."""

    def __init__(
        self,
        dataset_root: Path,
        world: WorldManifest,
        *,
        max_record_chars: int = 50_000,
    ) -> None:
        if max_record_chars < 1:
            raise ValueError("max_record_chars must be positive")
        verify_world_artifacts(dataset_root, world)
        self._max_record_chars = max_record_chars
        self._records = _load_world_records(dataset_root, world, max_record_chars)

    def resolve(self, evidence_refs: Iterable[str]) -> tuple[ResolvedEvidence, ...]:
        resolution = self.resolve_observation(evidence_refs)
        if resolution.unknown_refs:
            raise KeyError(
                f"unknown canonical evidence refs: {list(resolution.unknown_refs)}"
            )
        return resolution.resolved

    def resolve_observation(self, evidence_refs: Iterable[str]) -> EvidenceResolution:
        """Resolve a run without turning hallucinated refs into grader failures."""

        refs = tuple(evidence_refs)
        if len(refs) != len(set(refs)):
            raise ValueError("evidence refs must be unique")
        unknown = tuple(ref for ref in refs if ref not in self._records)
        return EvidenceResolution(
            resolved=tuple(self._records[ref] for ref in refs if ref in self._records),
            unknown_refs=unknown,
        )


def _load_world_records(
    dataset_root: Path,
    world: WorldManifest,
    max_record_chars: int,
) -> dict[str, ResolvedEvidence]:
    resolved: dict[str, ResolvedEvidence] = {}
    for artifact in world.artifacts:
        path = (dataset_root / artifact.path).resolve()
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            record = json.loads(line)
            aliases = _record_aliases(record)
            if not aliases:
                raise ValueError(
                    f"world record has no resolvable id: {artifact.role}:{line_number}"
                )
            evidence = _resolved_record(artifact.role, record, max_record_chars)
            for alias in aliases:
                existing = resolved.get(alias)
                if (
                    existing is not None
                    and existing.record_fingerprint != evidence.record_fingerprint
                ):
                    raise ValueError(f"ambiguous world evidence ref: {alias}")
                resolved[alias] = evidence.model_copy(update={"evidence_ref": alias})
    return resolved


def _record_aliases(record: Mapping[str, object]) -> tuple[str, ...]:
    values = []
    for field in ("document_key", "id"):
        value = record.get(field)
        if isinstance(value, str) and value:
            values.append(value)
    return tuple(dict.fromkeys(values))


def _resolved_record(
    role: str, record: Mapping[str, object], max_record_chars: int
) -> ResolvedEvidence:
    canonical = json.dumps(
        record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if len(canonical) > max_record_chars:
        raise ValueError(f"world evidence record exceeds {max_record_chars} characters")
    content = _content_for_role(role, record, canonical)
    fingerprint = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    primary_ref = str(record.get("document_key") or record.get("id"))
    title = record.get("title")
    return ResolvedEvidence(
        evidence_ref=primary_ref,
        artifact_role=role,
        title=title if isinstance(title, str) else None,
        content=content,
        record_fingerprint=fingerprint,
    )


def _content_for_role(
    role: str, record: Mapping[str, object], canonical: str
) -> str:
    if role == "documents":
        parts = [
            str(record[field])
            for field in ("title", "document_type", "published_on", "content")
            if record.get(field) not in (None, "")
        ]
        return "\n".join(parts)
    if role == "semantic_relation_annotations":
        return "\n".join(
            str(record[field])
            for field in (
                "source_node_key",
                "relation_type",
                "target_node_key",
                "description",
            )
            if record.get(field) not in (None, "")
        )
    return canonical
