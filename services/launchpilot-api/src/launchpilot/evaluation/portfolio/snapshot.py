from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MANIFEST_SCHEMA = "launchpilot.eval-snapshot"
MANIFEST_SCHEMA_VERSION = 1

ArtifactCategory = Literal["dataset", "result"]
ScopeKind = Literal["file", "directory"]


def _relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or "\x00" in value
        or path.is_absolute()
        or value in {".", ".."}
        or ".." in path.parts
        or path.as_posix() != value
    ):
        raise ValueError("expected a canonical POSIX path below the snapshot root")
    return value


class SnapshotScope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    relative_path: str
    category: ArtifactCategory
    kind: ScopeKind | None = None

    _validate_path = field_validator("relative_path")(_relative_path)


class SnapshotArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    relative_path: str
    category: ArtifactCategory
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)

    _validate_path = field_validator("relative_path")(_relative_path)


class SnapshotManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    manifest_schema: Literal["launchpilot.eval-snapshot"] = Field(alias="schema")
    schema_version: Literal[1]
    snapshot_version: str = Field(min_length=1)
    created_at: datetime
    scopes: tuple[SnapshotScope, ...] = Field(min_length=1)
    artifacts: tuple[SnapshotArtifact, ...] = ()

    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_canonical_contents(self) -> SnapshotManifest:
        scope_keys = [
            (scope.relative_path, scope.category, scope.kind or "")
            for scope in self.scopes
        ]
        artifact_paths = [artifact.relative_path for artifact in self.artifacts]
        if any(scope.kind is None for scope in self.scopes):
            raise ValueError("persisted scopes require a file or directory kind")
        if scope_keys != sorted(scope_keys) or len(scope_keys) != len(set(scope_keys)):
            raise ValueError("scopes must be unique and sorted")
        if artifact_paths != sorted(artifact_paths) or len(artifact_paths) != len(
            set(artifact_paths)
        ):
            raise ValueError("artifacts must have unique, sorted relative paths")

        for artifact in self.artifacts:
            categories = {
                scope.category
                for scope in self.scopes
                if artifact.relative_path == scope.relative_path
                or (
                    scope.kind == "directory"
                    and artifact.relative_path.startswith(f"{scope.relative_path}/")
                )
            }
            if categories != {artifact.category}:
                raise ValueError(
                    f"artifact has missing or ambiguous scope: {artifact.relative_path}"
                )
        return self


class SnapshotVerificationError(RuntimeError):
    def __init__(
        self,
        *,
        missing: Iterable[str] = (),
        modified: Iterable[str] = (),
        extra: Iterable[str] = (),
        scope_errors: Iterable[str] = (),
    ) -> None:
        self.missing = tuple(sorted(missing))
        self.modified = tuple(sorted(modified))
        self.extra = tuple(sorted(extra))
        self.scope_errors = tuple(sorted(set(scope_errors)))
        summary = ", ".join(
            f"{name}={len(paths)}"
            for name, paths in (
                ("missing", self.missing),
                ("modified", self.modified),
                ("extra", self.extra),
                ("scope_errors", self.scope_errors),
            )
            if paths
        )
        super().__init__(f"snapshot verification failed: {summary}")


HISTORICAL_SNAPSHOT_SCOPES: tuple[SnapshotScope, ...] = tuple(
    SnapshotScope(relative_path=path, category="dataset")
    for path in (
        "evals/golden/golden-v1",
        "evals/golden/golden-v2",
        "evals/golden/golden-v3",
    )
) + tuple(
    SnapshotScope(relative_path=f"evals/{name}", category="result")
    for name in (
        "agentic_benchmark_results_v2.json",
        "agentic_progressive_ablation_results.json",
        "phase2_ablation_results.json",
        "phase3_ablation_results.json",
        "retrieval_benchmark_v3_results.json",
        "retrieval_experiment_results_v2.json",
        "scale_benchmark_n20_results.json",
        "stress_test_comparison_results.json",
    )
)


def _excluded(path: Path) -> bool:
    name = path.name
    return (
        any(part in {".git", "__pycache__"} for part in path.parts)
        or name == ".env"
        or name.startswith(".env.")
        or path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}
    )


def _root(root: str | Path) -> Path:
    path = Path(root).resolve(strict=True)
    if not path.is_dir():
        raise NotADirectoryError(f"snapshot root is not a directory: {path}")
    return path


def _scan_scope(
    root: Path,
    scope: SnapshotScope,
    *,
    tolerate_errors: bool,
) -> tuple[ScopeKind | None, tuple[Path, ...], str | None]:
    path = root.joinpath(*PurePosixPath(scope.relative_path).parts)
    if not path.resolve(strict=False).is_relative_to(root):
        raise ValueError(f"snapshot scope escapes its root: {scope.relative_path}")
    if not path.exists():
        if tolerate_errors:
            return None, (), f"missing scope: {scope.relative_path}"
        raise FileNotFoundError(f"snapshot scope does not exist: {scope.relative_path}")
    if path.is_symlink() or _excluded(path.relative_to(root)):
        message = f"unsafe snapshot scope: {scope.relative_path}"
        if tolerate_errors:
            return None, (), message
        raise ValueError(message)

    kind: ScopeKind = "file" if path.is_file() else "directory"
    error = None
    if scope.kind is not None and scope.kind != kind:
        error = f"scope type changed: {scope.relative_path}"
    candidates = (path,) if kind == "file" else tuple(path.rglob("*"))
    files = tuple(
        sorted(
            (
                candidate
                for candidate in candidates
                if candidate.is_file()
                and not candidate.is_symlink()
                and not _excluded(candidate.relative_to(root))
            ),
            key=lambda candidate: candidate.relative_to(root).as_posix(),
        )
    )
    return kind, files, error


def _fingerprint(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size_bytes = 0
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
            size_bytes += len(chunk)
    return digest.hexdigest(), size_bytes


def _artifact(root: Path, path: Path, category: ArtifactCategory) -> SnapshotArtifact:
    sha256, size_bytes = _fingerprint(path)
    return SnapshotArtifact(
        relative_path=path.relative_to(root).as_posix(),
        category=category,
        sha256=sha256,
        size_bytes=size_bytes,
    )


def create_manifest(
    root: str | Path,
    scopes: Iterable[SnapshotScope],
    *,
    snapshot_version: str,
    created_at: datetime,
) -> SnapshotManifest:
    """Create a deterministic checksum manifest from explicitly selected paths."""

    root_path = _root(root)
    requests = tuple(scopes)
    if not requests:
        raise ValueError("at least one snapshot scope is required")

    resolved_scopes: dict[tuple[str, str, str], SnapshotScope] = {}
    artifacts: dict[str, SnapshotArtifact] = {}
    for request in requests:
        kind, files, _ = _scan_scope(root_path, request, tolerate_errors=False)
        scope = request.model_copy(update={"kind": kind})
        resolved_scopes[(scope.relative_path, scope.category, scope.kind or "")] = scope
        for path in files:
            relative_path = path.relative_to(root_path).as_posix()
            if relative_path in artifacts:
                if artifacts[relative_path].category != scope.category:
                    raise ValueError(f"conflicting scope categories: {relative_path}")
                continue
            artifacts[relative_path] = _artifact(root_path, path, scope.category)

    return SnapshotManifest(
        schema=MANIFEST_SCHEMA,
        schema_version=MANIFEST_SCHEMA_VERSION,
        snapshot_version=snapshot_version,
        created_at=created_at,
        scopes=tuple(resolved_scopes[key] for key in sorted(resolved_scopes)),
        artifacts=tuple(artifacts[path] for path in sorted(artifacts)),
    )


def verify_manifest(root: str | Path, manifest: SnapshotManifest) -> None:
    """Raise with all missing, modified, and extra paths when the snapshot drifts."""

    root_path = _root(root)
    actual: dict[str, SnapshotArtifact] = {}
    scope_errors: list[str] = []
    for scope in manifest.scopes:
        _, files, error = _scan_scope(root_path, scope, tolerate_errors=True)
        if error:
            scope_errors.append(error)
        for path in files:
            relative_path = path.relative_to(root_path).as_posix()
            if (
                relative_path in actual
                and actual[relative_path].category != scope.category
            ):
                scope_errors.append(f"conflicting current categories: {relative_path}")
                continue
            actual[relative_path] = _artifact(root_path, path, scope.category)

    expected = {artifact.relative_path: artifact for artifact in manifest.artifacts}
    expected_paths, actual_paths = set(expected), set(actual)
    modified = {
        path
        for path in expected_paths & actual_paths
        if expected[path].sha256 != actual[path].sha256
        or expected[path].size_bytes != actual[path].size_bytes
    }
    missing = expected_paths - actual_paths
    extra = actual_paths - expected_paths
    if missing or modified or extra or scope_errors:
        raise SnapshotVerificationError(
            missing=missing,
            modified=modified,
            extra=extra,
            scope_errors=scope_errors,
        )


def manifest_to_json(manifest: SnapshotManifest) -> str:
    payload = manifest.model_dump(mode="json", by_alias=True)
    payload["created_at"] = manifest.created_at.isoformat().replace("+00:00", "Z")
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def manifest_from_json(payload: str | bytes) -> SnapshotManifest:
    return SnapshotManifest.model_validate_json(payload)


def write_manifest(path: Path, manifest: SnapshotManifest) -> None:
    if path.exists():
        raise FileExistsError(f"snapshot manifest already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest_to_json(manifest), encoding="utf-8")


def load_manifest(path: Path) -> SnapshotManifest:
    return manifest_from_json(path.read_text(encoding="utf-8"))
