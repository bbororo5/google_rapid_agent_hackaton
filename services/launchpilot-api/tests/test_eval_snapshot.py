from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from launchpilot.evaluation.portfolio.snapshot import (
    HISTORICAL_SNAPSHOT_SCOPES,
    SnapshotManifest,
    SnapshotScope,
    SnapshotVerificationError,
    create_manifest,
    load_manifest,
    manifest_from_json,
    manifest_to_json,
    verify_manifest,
    write_manifest,
)

CREATED_AT = datetime(2026, 8, 27, 3, 4, 5, tzinfo=UTC)


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _manifest(root: Path) -> SnapshotManifest:
    return create_manifest(
        root,
        (
            SnapshotScope(relative_path="golden", category="dataset"),
            SnapshotScope(relative_path="results/run.json", category="result"),
        ),
        snapshot_version="historical-v1",
        created_at=CREATED_AT,
    )


def test_manifest_is_deterministic_sorted_and_content_addressed(tmp_path: Path) -> None:
    _write(tmp_path / "golden/z.jsonl", b"z\n")
    _write(tmp_path / "golden/a.jsonl", b"alpha\n")
    _write(tmp_path / "results/run.json", b'{"score": 1}\n')

    manifest = _manifest(tmp_path)
    reversed_manifest = create_manifest(
        tmp_path,
        reversed(
            (
                SnapshotScope(relative_path="golden", category="dataset"),
                SnapshotScope(relative_path="results/run.json", category="result"),
            )
        ),
        snapshot_version="historical-v1",
        created_at=CREATED_AT,
    )

    assert manifest == reversed_manifest
    assert [artifact.relative_path for artifact in manifest.artifacts] == [
        "golden/a.jsonl",
        "golden/z.jsonl",
        "results/run.json",
    ]
    assert manifest.artifacts[0].sha256 == hashlib.sha256(b"alpha\n").hexdigest()
    assert manifest.artifacts[0].size_bytes == 6
    assert [artifact.category for artifact in manifest.artifacts] == [
        "dataset",
        "dataset",
        "result",
    ]

    serialized = manifest_to_json(manifest)
    assert '"created_at": "2026-08-27T03:04:05Z"' in serialized
    assert manifest_from_json(serialized) == manifest
    assert manifest_to_json(manifest_from_json(serialized)) == serialized

    path = tmp_path / "manifests/historical-v1.json"
    write_manifest(path, manifest)
    assert load_manifest(path) == manifest
    with pytest.raises(FileExistsError):
        write_manifest(path, manifest)


def test_verification_fails_for_missing_modified_and_extra_files(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "golden/missing.jsonl", b"remove me")
    _write(tmp_path / "golden/modified.jsonl", b"before")
    _write(tmp_path / "results/run.json", b"stable")
    manifest = _manifest(tmp_path)

    (tmp_path / "golden/missing.jsonl").unlink()
    _write(tmp_path / "golden/modified.jsonl", b"after")
    _write(tmp_path / "golden/extra.jsonl", b"new")

    with pytest.raises(SnapshotVerificationError) as caught:
        verify_manifest(tmp_path, manifest)
    assert caught.value.missing == ("golden/missing.jsonl",)
    assert caught.value.modified == ("golden/modified.jsonl",)
    assert caught.value.extra == ("golden/extra.jsonl",)


def test_verification_fails_when_an_explicit_scope_disappears(tmp_path: Path) -> None:
    _write(tmp_path / "golden/case.jsonl", b"case")
    _write(tmp_path / "results/run.json", b"result")
    manifest = _manifest(tmp_path)
    verify_manifest(tmp_path, manifest)

    (tmp_path / "results/run.json").unlink()
    with pytest.raises(SnapshotVerificationError) as caught:
        verify_manifest(tmp_path, manifest)
    assert caught.value.missing == ("results/run.json",)
    assert caught.value.scope_errors == ("missing scope: results/run.json",)


def test_schema_and_timestamp_are_explicit_and_validated(tmp_path: Path) -> None:
    _write(tmp_path / "golden/case.jsonl", b"case")
    scope = SnapshotScope(relative_path="golden", category="dataset")
    with pytest.raises(ValidationError, match="timezone"):
        create_manifest(
            tmp_path,
            (scope,),
            snapshot_version="v1",
            created_at=CREATED_AT.replace(tzinfo=None),
        )

    manifest = create_manifest(
        tmp_path,
        (scope,),
        snapshot_version="v1",
        created_at=CREATED_AT,
    )
    unsupported = manifest.model_dump(mode="json") | {"schema_version": 2}
    with pytest.raises(ValidationError):
        SnapshotManifest.model_validate(unsupported)


def test_scan_omits_secrets_runtime_databases_and_symlinks(tmp_path: Path) -> None:
    _write(tmp_path / "golden/case.jsonl", b"case")
    _write(tmp_path / "golden/.env", b"SECRET=value")
    _write(tmp_path / "golden/runtime.db", b"database")
    (tmp_path / "golden/link.jsonl").symlink_to(tmp_path / "golden/case.jsonl")
    _write(tmp_path / "results/run.json", b"result")

    assert [artifact.relative_path for artifact in _manifest(tmp_path).artifacts] == [
        "golden/case.jsonl",
        "results/run.json",
    ]


def test_historical_scopes_cover_all_existing_golden_versions_and_results() -> None:
    service_root = Path(__file__).parents[1]
    manifest = create_manifest(
        service_root,
        HISTORICAL_SNAPSHOT_SCOPES,
        snapshot_version="pre-redesign-historical-v1",
        created_at=CREATED_AT,
    )

    assert {
        scope.relative_path
        for scope in HISTORICAL_SNAPSHOT_SCOPES
        if scope.category == "dataset"
    } == {
        "evals/golden/golden-v1",
        "evals/golden/golden-v2",
        "evals/golden/golden-v3",
    }
    assert {
        scope.relative_path
        for scope in HISTORICAL_SNAPSHOT_SCOPES
        if scope.category == "result"
    } == {
        path.relative_to(service_root).as_posix()
        for path in (service_root / "evals").glob("*results*.json")
    }
    assert {artifact.category for artifact in manifest.artifacts} == {
        "dataset",
        "result",
    }
    verify_manifest(service_root, manifest)
