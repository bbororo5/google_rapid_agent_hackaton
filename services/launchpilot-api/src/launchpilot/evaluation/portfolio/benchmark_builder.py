"""Deterministic candidate portfolios derived from the frozen golden-v2 cases.

This module deliberately selects on problem and review characteristics only.  Tool
names, expected routes, and observed system results are not inputs to the policy.
The output is a *candidate* manifest: cases that still need human review retain that
gate even when they are useful safety cases selected for the frozen portfolio.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

POLICY_VERSION = "golden-v2-portfolio-v0"

Disposition = Literal["frozen_v0", "holdout", "not_selected"]
CandidateClass = Literal[
    "auto_validatable", "high_value_safety", "not_frozen_eligible"
]
Readiness = Literal["ready", "pending_human_review"]

_UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    flags=re.IGNORECASE,
)
_CAMPAIGN_CODE_PATTERN = re.compile(r"c\d{4}", flags=re.IGNORECASE)
_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")


@dataclass(frozen=True)
class PortfolioPolicy:
    """Small policy surface for the first candidate portfolio.

    The two frozen limits make the review gate visible.  Increasing
    ``frozen_safety_review_limit`` adds review work; it does not turn those cases
    into benchmark-ready truth.
    """

    frozen_auto_validated_limit: int = 48
    frozen_safety_review_limit: int = 16
    holdout_target_size: int = 50
    selection_salt: str = POLICY_VERSION
    safety_answer_modes: tuple[str, ...] = (
        "abstention",
        "clarification",
        "data_quality_alert",
    )
    safety_query_profiles: tuple[str, ...] = (
        "adversarial",
        "ambiguous",
        "no_answer",
    )

    def __post_init__(self) -> None:
        numeric_values = (
            self.frozen_auto_validated_limit,
            self.frozen_safety_review_limit,
            self.holdout_target_size,
        )
        if any(value < 0 for value in numeric_values):
            raise ValueError("portfolio size limits must be non-negative")
        if not self.selection_salt:
            raise ValueError("selection_salt must not be empty")


@dataclass(frozen=True)
class SelectionRecord:
    """Auditable disposition for one source case."""

    case_id: str
    disposition: Disposition
    candidate_class: CandidateClass
    validation_status: str
    readiness: Readiness
    human_review_required: bool
    selection_reasons: tuple[str, ...]
    leakage_component_id: str
    leakage_keys: tuple[str, ...]
    query_profile: str
    analysis_task: str
    answer_mode: str
    risk_types: tuple[str, ...]


@dataclass(frozen=True)
class BenchmarkPortfolioManifest:
    """Selection result plus enough provenance to reproduce and audit it."""

    policy_version: str
    dataset_version: str
    dataset_fingerprint: str
    source_case_count: int
    policy: PortfolioPolicy
    leakage_component_count: int
    largest_leakage_component_size: int
    holdout_target_delta: int
    records: tuple[SelectionRecord, ...]

    @property
    def warnings(self) -> tuple[str, ...]:
        warnings = []
        if self.largest_leakage_component_size / self.source_case_count >= 0.8:
            warnings.append("source_dataset_has_giant_leakage_component")
        holdout_profiles = {record.query_profile for record in self.holdout_records}
        if len(holdout_profiles) <= 1:
            warnings.append("holdout_is_not_distribution_representative")
        if self.holdout_records and all(
            record.human_review_required for record in self.holdout_records
        ):
            warnings.append("holdout_is_fully_pending_human_review")
        if any(record.human_review_required for record in self.frozen_records):
            warnings.append("frozen_candidate_contains_review_gated_cases")
        return tuple(warnings)

    @property
    def frozen_records(self) -> tuple[SelectionRecord, ...]:
        return tuple(
            record for record in self.records if record.disposition == "frozen_v0"
        )

    @property
    def holdout_records(self) -> tuple[SelectionRecord, ...]:
        return tuple(
            record for record in self.records if record.disposition == "holdout"
        )

    @property
    def human_review_queue(self) -> tuple[SelectionRecord, ...]:
        return tuple(
            record
            for record in self.records
            if record.disposition != "not_selected"
            and record.human_review_required
        )

    def to_dict(
        self,
        *,
        include_leakage_keys: bool = False,
        include_unselected_records: bool = False,
    ) -> dict[str, Any]:
        """Serialize a compact audit view unless full leakage keys are requested.

        Full keys remain available on ``records`` for in-memory invariant checks.
        Omitting them from committed manifests keeps routine human review tractable.
        """

        dispositions: dict[str, int] = defaultdict(int)
        readiness: dict[str, int] = defaultdict(int)
        for record in self.records:
            dispositions[record.disposition] += 1
            if record.disposition != "not_selected":
                readiness[record.readiness] += 1
        serialized_records = (
            self.records
            if include_unselected_records
            else tuple(
                record
                for record in self.records
                if record.disposition != "not_selected"
            )
        )
        omitted_case_ids = tuple(
            record.case_id
            for record in self.records
            if record not in serialized_records
        )
        return {
            "policy_version": self.policy_version,
            "dataset_version": self.dataset_version,
            "dataset_fingerprint": self.dataset_fingerprint,
            "source_case_count": self.source_case_count,
            "policy": asdict(self.policy),
            "leakage_summary": {
                "component_count": self.leakage_component_count,
                "largest_component_size": self.largest_leakage_component_size,
                "holdout_target_delta": self.holdout_target_delta,
            },
            "selection_summary": {
                "by_disposition": dict(sorted(dispositions.items())),
                "by_readiness": dict(sorted(readiness.items())),
                "human_review_queue_size": len(self.human_review_queue),
            },
            "warnings": self.warnings,
            "records": [
                _serialize_record(
                    record,
                    include_leakage_keys=include_leakage_keys,
                )
                for record in serialized_records
            ],
            "omitted_record_summary": {
                "disposition": "not_selected",
                "count": len(omitted_case_ids),
                "case_id_fingerprint": hashlib.sha256(
                    "\0".join(omitted_case_ids).encode()
                ).hexdigest(),
            },
        }


def write_benchmark_manifest(
    path: Path, manifest: BenchmarkPortfolioManifest
) -> None:
    if path.exists():
        raise FileExistsError(f"benchmark portfolio manifest already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def _serialize_record(
    record: SelectionRecord, *, include_leakage_keys: bool
) -> dict[str, Any]:
    serialized = asdict(record)
    serialized["leakage_key_count"] = len(record.leakage_keys)
    if not include_leakage_keys:
        del serialized["leakage_keys"]
    return serialized


def load_cases(path: Path) -> tuple[dict[str, Any], ...]:
    """Load JSONL without coupling the selector to a repository-relative path."""

    return tuple(
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def template_style_key(case_id: str) -> str:
    """Collapse generated entity/number tokens while retaining the task family."""

    normalized = _UUID_PATTERN.sub("<uuid>", case_id.casefold())
    normalized = _CAMPAIGN_CODE_PATTERN.sub("c#", normalized)
    normalized = _NUMBER_PATTERN.sub("#", normalized)
    return normalized


def leakage_keys(case: Mapping[str, Any]) -> tuple[str, ...]:
    """Return conservative declared, entity, source, and template-style keys."""

    keys = {
        f"declared:{value}"
        for value in _string_values(case.get("leakage_group_ids", ()))
    }

    scope = _mapping(case.get("scope"))
    filters = _mapping(case.get("filters"))
    ambiguity = _mapping(case.get("ambiguity"))
    for container, names in (
        (scope, ("campaign_id", "campaign_ref")),
        (
            filters,
            (
                "campaign_id",
                "campaign_ids",
                "campaign_ref",
                "campaign_refs",
                "campaign_alias",
            ),
        ),
        (ambiguity, ("candidate_campaign_ids",)),
    ):
        for name in names:
            for value in _string_values(container.get(name, ())):
                keys.add(f"entity:{value.casefold()}")

    for evidence in case.get("gold_evidence", ()):
        if not isinstance(evidence, Mapping):
            continue
        corpus_ref = evidence.get("corpus_ref")
        if isinstance(corpus_ref, str) and corpus_ref:
            keys.add(f"source:{corpus_ref}")

    case_id = case.get("case_id")
    if isinstance(case_id, str) and case_id:
        keys.add(f"template_style:{template_style_key(case_id)}")
    return tuple(sorted(keys))


def build_benchmark_portfolio(
    cases: Sequence[Mapping[str, Any]],
    policy: PortfolioPolicy | None = None,
) -> BenchmarkPortfolioManifest:
    """Build deterministic Frozen-v0 and leakage-disjoint Holdout candidates."""

    active_policy = policy or PortfolioPolicy()
    ordered_cases = _validate_and_order_cases(cases)
    keys_by_case = {case["case_id"]: leakage_keys(case) for case in ordered_cases}
    components, component_by_case = _connected_components(
        tuple(case["case_id"] for case in ordered_cases), keys_by_case
    )

    holdout_component_ids = _choose_holdout_components(
        components,
        active_policy.holdout_target_size,
        active_policy.selection_salt,
    )
    holdout_ids = {
        case_id
        for component_id in holdout_component_ids
        for case_id in components[component_id]
    }
    frozen_pool = [case for case in ordered_cases if case["case_id"] not in holdout_ids]

    auto_candidates = [
        case for case in frozen_pool if case["validation_status"] == "auto_validated"
    ]
    safety_candidates = [
        case
        for case in frozen_pool
        if case["validation_status"] != "auto_validated"
        and _is_high_value_safety(case, active_policy)
    ]
    frozen_auto_ids = {
        case["case_id"]
        for case in _balanced_sample(
            auto_candidates,
            active_policy.frozen_auto_validated_limit,
            active_policy.selection_salt + ":frozen:auto",
        )
    }
    frozen_safety_ids = {
        case["case_id"]
        for case in _balanced_sample(
            safety_candidates,
            active_policy.frozen_safety_review_limit,
            active_policy.selection_salt + ":frozen:safety",
        )
    }
    frozen_ids = frozen_auto_ids | frozen_safety_ids

    records = tuple(
        _selection_record(
            case,
            keys_by_case[case["case_id"]],
            component_by_case[case["case_id"]],
            frozen_auto_ids,
            frozen_safety_ids,
            holdout_ids,
            active_policy,
        )
        for case in ordered_cases
    )
    holdout_actual_size = len(holdout_ids)
    manifest = BenchmarkPortfolioManifest(
        policy_version=POLICY_VERSION,
        dataset_version=str(ordered_cases[0]["golden_version"]),
        dataset_fingerprint=_dataset_fingerprint(ordered_cases),
        source_case_count=len(ordered_cases),
        policy=active_policy,
        leakage_component_count=len(components),
        largest_leakage_component_size=max(map(len, components.values())),
        holdout_target_delta=holdout_actual_size - active_policy.holdout_target_size,
        records=records,
    )
    assert_no_portfolio_leakage(manifest)
    if len(frozen_ids) != len(frozen_auto_ids) + len(frozen_safety_ids):
        raise AssertionError("frozen candidate classes unexpectedly overlap")
    return manifest


def assert_no_portfolio_leakage(manifest: BenchmarkPortfolioManifest) -> None:
    """Fail if Frozen and Holdout share a case, component, or leakage key."""

    frozen = manifest.frozen_records
    holdout = manifest.holdout_records
    frozen_ids = {record.case_id for record in frozen}
    holdout_ids = {record.case_id for record in holdout}
    if overlap := frozen_ids & holdout_ids:
        raise AssertionError(f"case overlap between Frozen and Holdout: {sorted(overlap)}")

    frozen_components = {record.leakage_component_id for record in frozen}
    holdout_components = {record.leakage_component_id for record in holdout}
    if overlap := frozen_components & holdout_components:
        raise AssertionError(
            "leakage component overlap between Frozen and Holdout: "
            f"{sorted(overlap)}"
        )

    frozen_keys = {key for record in frozen for key in record.leakage_keys}
    holdout_keys = {key for record in holdout for key in record.leakage_keys}
    if overlap := frozen_keys & holdout_keys:
        raise AssertionError(
            f"leakage keys shared by Frozen and Holdout: {sorted(overlap)}"
        )


def _validate_and_order_cases(
    cases: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    if not cases:
        raise ValueError("at least one golden-v2 case is required")
    required_fields = {
        "case_id",
        "golden_version",
        "validation_status",
        "query_profile",
        "analysis_task",
        "answer_mode",
        "risk_types",
        "leakage_group_ids",
        "gold_evidence",
    }
    case_ids: list[str] = []
    versions: set[str] = set()
    for case in cases:
        if missing := required_fields - case.keys():
            raise ValueError(f"golden-v2 case missing fields: {sorted(missing)}")
        case_id = case["case_id"]
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("case_id must be a non-empty string")
        case_ids.append(case_id)
        versions.add(str(case["golden_version"]))
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("case_id values must be unique")
    if versions != {"golden-v2"}:
        raise ValueError(f"expected only golden-v2 cases, received {sorted(versions)}")
    return tuple(sorted(cases, key=lambda case: str(case["case_id"])))


def _connected_components(
    case_ids: tuple[str, ...],
    keys_by_case: Mapping[str, tuple[str, ...]],
) -> tuple[dict[str, tuple[str, ...]], dict[str, str]]:
    parent = {case_id: case_id for case_id in case_ids}

    def find(case_id: str) -> str:
        while parent[case_id] != case_id:
            parent[case_id] = parent[parent[case_id]]
            case_id = parent[case_id]
        return case_id

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    owner_by_key: dict[str, str] = {}
    for case_id in case_ids:
        for key in keys_by_case[case_id]:
            owner = owner_by_key.setdefault(key, case_id)
            union(case_id, owner)

    members_by_root: dict[str, list[str]] = defaultdict(list)
    for case_id in case_ids:
        members_by_root[find(case_id)].append(case_id)

    components: dict[str, tuple[str, ...]] = {}
    component_by_case: dict[str, str] = {}
    for members in members_by_root.values():
        ordered_members = tuple(sorted(members))
        digest = hashlib.sha256("\0".join(ordered_members).encode()).hexdigest()[:16]
        component_id = f"component:{digest}"
        components[component_id] = ordered_members
        component_by_case.update(dict.fromkeys(ordered_members, component_id))
    return dict(sorted(components.items())), component_by_case


def _choose_holdout_components(
    components: Mapping[str, tuple[str, ...]], target_size: int, salt: str
) -> tuple[str, ...]:
    if target_size == 0:
        return ()
    ranked = sorted(
        components,
        key=lambda component_id: _stable_rank(salt + ":holdout", component_id),
    )
    # The collection is small (680 cases), so exact subset-size dynamic programming
    # gives a closer target than greedy selection while never splitting a component.
    reachable: dict[int, tuple[int, ...]] = {0: ()}
    for rank, component_id in enumerate(ranked):
        size = len(components[component_id])
        additions: dict[int, tuple[int, ...]] = {}
        for total, selected_ranks in tuple(reachable.items()):
            candidate_total = total + size
            candidate = (*selected_ranks, rank)
            current = reachable.get(candidate_total) or additions.get(candidate_total)
            if current is None or candidate < current:
                additions[candidate_total] = candidate
        for total, candidate in additions.items():
            current = reachable.get(total)
            if current is None or candidate < current:
                reachable[total] = candidate

    selected_total = min(
        reachable,
        key=lambda total: (
            abs(total - target_size),
            total > target_size,
            reachable[total],
        ),
    )
    return tuple(ranked[rank] for rank in reachable[selected_total])


def _balanced_sample(
    cases: Sequence[Mapping[str, Any]], limit: int, salt: str
) -> tuple[Mapping[str, Any], ...]:
    if limit == 0:
        return ()
    buckets: dict[tuple[str, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for case in cases:
        stratum = (
            str(case["query_profile"]),
            str(case["analysis_task"]),
            str(case["answer_mode"]),
        )
        buckets[stratum].append(case)
    for stratum, members in buckets.items():
        members.sort(
            key=lambda case: _stable_rank(
                salt + ":case:" + "|".join(stratum), str(case["case_id"])
            )
        )

    ordered_strata = sorted(
        buckets,
        key=lambda stratum: _stable_rank(salt + ":stratum", "|".join(stratum)),
    )
    selected: list[Mapping[str, Any]] = []
    cursor = 0
    while len(selected) < limit and ordered_strata:
        next_round: list[tuple[str, ...]] = []
        for stratum in ordered_strata:
            members = buckets[stratum]
            if cursor < len(members):
                selected.append(members[cursor])
                if len(selected) == limit:
                    break
            if cursor + 1 < len(members):
                next_round.append(stratum)
        else:
            ordered_strata = next_round
            cursor += 1
            continue
        break
    return tuple(selected)


def _is_high_value_safety(
    case: Mapping[str, Any], policy: PortfolioPolicy
) -> bool:
    risk_types = set(_string_values(case.get("risk_types", ()))) - {"none"}
    return bool(
        risk_types
        or case.get("unanswerable") is True
        or case.get("answer_mode") in policy.safety_answer_modes
        or case.get("query_profile") in policy.safety_query_profiles
    )


def _selection_record(
    case: Mapping[str, Any],
    case_leakage_keys: tuple[str, ...],
    component_id: str,
    frozen_auto_ids: set[str],
    frozen_safety_ids: set[str],
    holdout_ids: set[str],
    policy: PortfolioPolicy,
) -> SelectionRecord:
    case_id = str(case["case_id"])
    validation_status = str(case["validation_status"])
    human_review_required = validation_status not in {
        "auto_validated",
        "human_reviewed",
    }
    if validation_status == "auto_validated":
        candidate_class: CandidateClass = "auto_validatable"
    elif _is_high_value_safety(case, policy):
        candidate_class = "high_value_safety"
    else:
        candidate_class = "not_frozen_eligible"

    if case_id in holdout_ids:
        disposition: Disposition = "holdout"
        reasons = ("leakage_component_selected_for_holdout",)
    elif case_id in frozen_auto_ids:
        disposition = "frozen_v0"
        reasons = ("auto_validated", "compact_stratified_sample")
    elif case_id in frozen_safety_ids:
        disposition = "frozen_v0"
        reasons = (
            "high_value_safety_case",
            "compact_stratified_sample",
            "human_review_gate_preserved",
        )
    else:
        disposition = "not_selected"
        reasons = ("outside_compact_candidate",)

    return SelectionRecord(
        case_id=case_id,
        disposition=disposition,
        candidate_class=candidate_class,
        validation_status=validation_status,
        readiness="pending_human_review" if human_review_required else "ready",
        human_review_required=human_review_required,
        selection_reasons=reasons,
        leakage_component_id=component_id,
        leakage_keys=case_leakage_keys,
        query_profile=str(case["query_profile"]),
        analysis_task=str(case["analysis_task"]),
        answer_mode=str(case["answer_mode"]),
        risk_types=tuple(_string_values(case.get("risk_types", ()))),
    )


def _dataset_fingerprint(cases: Iterable[Mapping[str, Any]]) -> str:
    canonical = "\n".join(
        json.dumps(case, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for case in cases
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _stable_rank(salt: str, value: str) -> str:
    return hashlib.sha256(f"{salt}\0{value}".encode()).hexdigest()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string_values(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Iterable) and not isinstance(value, Mapping):
        return tuple(item for item in value if isinstance(item, str) and item)
    return ()
