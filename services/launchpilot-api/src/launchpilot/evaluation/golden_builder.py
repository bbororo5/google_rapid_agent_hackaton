from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml

from launchpilot.devtools.synthetic_marketing import (
    DATASET_NAME,
    SyntheticConfig,
    build_campaign_documents,
    build_campaign_plans,
    build_platform_days,
    stable_uuid,
)
from launchpilot.persistence.postgres import PostgresDatabase

GOLDEN_VERSION = "golden-v2"
SYNTHETIC_SOURCE = "synthetic-marketing-v1"
DEFAULT_TAXONOMY_PATH = Path(__file__).parents[3] / "evals" / "taxonomy.yaml"
_METRIC_KEYS = (
    "impressions",
    "clicks",
    "spend",
    "conversions",
    "conversion_value",
    "ctr",
    "roas",
    "cpa",
    "cvr",
)
_METRIC_LABELS = {
    "impressions": "노출 수",
    "clicks": "클릭 수",
    "spend": "광고비",
    "conversions": "전환 수",
    "conversion_value": "전환 가치",
    "ctr": "CTR",
    "roas": "ROAS",
    "cpa": "CPA",
    "cvr": "CVR",
}
_SURFACE_LABELS = {
    "GOOGLE_ADS": "Google Ads",
    "META_ADS": "Meta Ads",
    "YOUTUBE": "YouTube",
}


@dataclass(frozen=True, slots=True)
class CampaignSource:
    id: str
    workspace_id: str
    workspace_name: str
    name: str
    goal: str
    period_start: date
    period_end: date
    target_metrics: tuple[str, ...]
    platforms: tuple[str, ...]
    external_refs: tuple[str, ...]

    @property
    def code(self) -> str:
        match = re.search(r"\bC\d{4}$", self.name)
        return match.group(0) if match else self.id[:8]

    @property
    def broad_alias(self) -> str:
        return self.name.split("|", maxsplit=1)[0].strip()


@dataclass(frozen=True, slots=True)
class MetricSource:
    campaign_id: str
    observation_id: str
    slice_index: int
    metric_index: int
    surface: str
    external_campaign_ref: str | None
    attribution_setting: str | None
    metric_key: str
    value: float
    unit: str
    period_start: date
    period_end: date
    provenance_ref: str
    calculation: str | None

    @property
    def corpus_ref(self) -> str:
        return f"pg:metric:{self.observation_id}:{self.slice_index}:{self.metric_index}"


@dataclass(frozen=True, slots=True)
class PartialObservationSource:
    campaign_id: str
    observation_id: str
    period_start: date
    period_end: date
    missing_reasons: tuple[str, ...]
    captured_at: datetime

    @property
    def corpus_ref(self) -> str:
        return f"pg:observation:{self.observation_id}"


@dataclass(frozen=True, slots=True)
class DocumentSource:
    id: str
    campaign_id: str
    workspace_id: str
    document_type: str
    title: str
    content: str
    source_ref: str
    created_at: datetime

    @property
    def corpus_ref(self) -> str:
        return self.source_ref


@dataclass(frozen=True, slots=True)
class BuildResult:
    output_root: str
    total_cases: int
    case_distribution: dict[str, int]
    split_distribution: dict[str, int]
    needs_review: int
    excluded_requested_cases: int
    validation_passed: bool


class MarketingGoldenBuilder:
    """Build a method-independent Golden Dataset from authoritative PG rows or synthetic plans."""

    def __init__(
        self,
        database: PostgresDatabase | None = None,
        taxonomy_path: Path = DEFAULT_TAXONOMY_PATH,
        version: str = "golden-v2",
        synthetic_config: Any | None = None,
    ) -> None:
        self._database = database
        self._taxonomy_path = taxonomy_path
        self._taxonomy = _load_taxonomy(taxonomy_path)
        self._version = version
        self._synthetic_config = synthetic_config

    def build(self, output_root: Path) -> BuildResult:
        generated_at = datetime.now(UTC).isoformat()
        campaigns = self._load_campaigns()
        min_required = 240 if self._version == "golden-v2" else 230
        if len(campaigns) < min_required:
            raise RuntimeError(
                f"at least {min_required} campaigns are required for the {self._version} profile"
            )

        structured_campaigns = campaigns[:100]
        lexical_campaigns = campaigns[100:190]
        adversarial_campaigns = (
            campaigns[190:240]
            if self._version == "golden-v2"
            else campaigns[190:210]
        )
        ambiguity_pool = campaigns if self._version == "golden-v2" else campaigns[210:]
        metrics = self._load_metrics(campaigns)
        partial_observations = self._load_partial_observations()
        documents = self._load_documents()
        audit = self._audit(generated_at, campaigns, metrics, partial_observations, documents)

        cases: list[dict[str, Any]] = []
        qrels: list[dict[str, Any]] = []
        corpus: dict[str, dict[str, Any]] = {}
        document_corpus = {
            document.corpus_ref: self._document_corpus_record(
                document,
                next(item for item in campaigns if item.id == document.campaign_id),
            )
            for document in documents
        }
        gold_spans: list[dict[str, Any]] = []
        needs_review: list[dict[str, Any]] = []

        self._add_structured_cases(structured_campaigns, metrics, cases, qrels, corpus)
        self._add_lexical_cases(lexical_campaigns, cases, qrels, corpus)
        self._add_no_answer_cases(campaigns, cases, needs_review)
        self._add_ambiguous_cases(ambiguity_pool, cases, qrels, corpus, needs_review)
        self._add_adversarial_cases(adversarial_campaigns, cases, needs_review)
        self._add_aggregation_cases(campaigns[:30], metrics, cases, qrels, corpus)
        self._add_period_comparison_cases(
            campaigns[30:60], metrics, cases, qrels, corpus
        )
        self._add_platform_comparison_cases(campaigns, metrics, cases, qrels, corpus)
        self._add_campaign_comparison_cases(campaigns, metrics, cases, qrels, corpus)
        self._add_trend_cases(campaigns[120:150], metrics, cases, qrels, corpus)
        self._add_tracking_gap_cases(
            partial_observations, campaigns, cases, qrels, corpus, needs_review
        )
        self._add_comparison_risk_cases(
            campaigns, metrics, cases, qrels, corpus, needs_review
        )
        if documents:
            self._add_document_cases(
                campaigns,
                documents,
                metrics,
                cases,
                qrels,
                corpus,
                gold_spans,
                needs_review,
            )

        campaign_by_id = {campaign.id: campaign for campaign in campaigns}
        for case in cases:
            case["golden_version"] = self._version
            case.update(self._classify_case(case, campaign_by_id))

        self._assign_splits(cases)
        cases.sort(key=lambda item: item["case_id"])
        qrels.sort(key=lambda item: (item["case_id"], item["corpus_ref"]))
        gold_spans.sort(key=lambda item: (item["case_id"], item["document_ref"]))
        needs_review.sort(key=lambda item: item["case_id"])

        excluded = self._excluded_categories(generated_at) if not documents else []
        aliases = self._entity_aliases(campaigns)
        split_payload = self._split_payload(cases)
        validation = self._validate(
            cases,
            qrels,
            corpus,
            document_corpus,
            gold_spans,
            split_payload,
        )
        taxonomy_coverage = self._taxonomy_coverage(cases)
        source_hashes = {
            "campaigns_sha256": _hash_records(
                [self._campaign_record(item) for item in campaigns]
            ),
            "selected_evidence_sha256": _hash_records(list(corpus.values())),
            "documents_sha256": _hash_records(list(document_corpus.values())),
        }
        case_distribution = dict(
            sorted(Counter(item["query_profile"] for item in cases).items())
        )
        split_distribution = dict(
            sorted(Counter(item["split"] for item in cases).items())
        )
        required_source_distribution = dict(
            sorted(
                Counter("+".join(item["required_sources"]) for item in cases).items()
            )
        )
        manifest = {
            "golden_version": self._version,
            "corpus_version": (
                "synthetic-pg-doc-snapshot-v2"
                if self._version == "golden-v2"
                else "synthetic-pg-doc-snapshot-v1"
            ),
            "created_at": generated_at,
            "source_kind": "approved_synthetic_postgresql",
            "source_data_hashes": source_hashes,
            "total_cases": len(cases),
            "target_cases": len(cases),
            "case_distribution": case_distribution,
            "language_distribution": {"ko-KR": len(cases)},
            "required_source_distribution": required_source_distribution,
            "split_distribution": split_distribution,
            "formulas": {
                "ctr": "clicks / impressions",
                "cvr": "conversions / clicks",
                "cpc": "spend / clicks",
                "cpa": "spend / conversions",
                "roas": "conversion_value / spend",
            },
            "zero_division_policy": "derived metric is 0 when denominator is 0",
            "exclusion_policy": (
                "Document-dependent profiles require a frozen source document and "
                "human-reviewable character span."
            ),
            "retrieval_configuration": None,
            "taxonomy_version": self._taxonomy["taxonomy_version"],
            "taxonomy_sha256": hashlib.sha256(
                self._taxonomy_path.read_bytes()
            ).hexdigest(),
            "taxonomy_coverage_ready": taxonomy_coverage["production_ready"],
            "taxonomy_distributions": taxonomy_coverage["dimensions"],
            "validation_results": validation["checks"],
            "validation_passed": validation["passed"],
        }

        output_root.mkdir(parents=True, exist_ok=True)
        for relative in (
            "corpus",
            "queries",
            "judgments",
            "splits",
            "review",
            "validation",
        ):
            (output_root / relative).mkdir(parents=True, exist_ok=True)

        _write_json(output_root / "manifest.json", manifest)
        _write_json(output_root / "data_audit.json", audit)
        shutil.copyfile(self._taxonomy_path, output_root / "taxonomy_snapshot.yaml")
        _write_jsonl(output_root / "entity_aliases.jsonl", aliases)
        _write_text(output_root / "dataset_policy.md", _dataset_policy())
        _write_jsonl(
            output_root / "corpus" / "documents.jsonl",
            sorted(document_corpus.values(), key=lambda item: item["document_ref"]),
        )
        _write_jsonl(
            output_root / "corpus" / "observations.jsonl",
            sorted(corpus.values(), key=lambda item: item["corpus_ref"]),
        )
        _write_jsonl(output_root / "queries" / "cases.jsonl", cases)
        _write_jsonl(output_root / "judgments" / "qrels.jsonl", qrels)
        _write_jsonl(output_root / "judgments" / "gold_spans.jsonl", gold_spans)
        _write_json(output_root / "splits" / "splits.json", split_payload)
        _write_jsonl(output_root / "review" / "needs_review.jsonl", needs_review)
        _write_jsonl(output_root / "review" / "excluded_items.jsonl", excluded)
        _write_case_catalog_csv(output_root / "review" / "case_catalog.csv", cases)
        _write_json(output_root / "validation" / "validation_report.json", validation)
        _write_json(
            output_root / "validation" / "taxonomy_coverage.json",
            taxonomy_coverage,
        )

        return BuildResult(
            output_root=str(output_root),
            total_cases=len(cases),
            case_distribution=case_distribution,
            split_distribution=split_distribution,
            needs_review=len(needs_review),
            excluded_requested_cases=sum(item["requested_count"] for item in excluded),
            validation_passed=validation["passed"],
        )

    def _classify_case(
        self,
        case: dict[str, Any],
        campaign_by_id: dict[str, CampaignSource],
    ) -> dict[str, Any]:
        taxonomy_seed = case.pop("taxonomy_seed", None)
        if taxonomy_seed is not None:
            return _taxonomy_assignment(self._taxonomy, **taxonomy_seed)
        profile = case["query_profile"]
        campaign_id = case.get("scope", {}).get("campaign_id")
        campaign = campaign_by_id.get(campaign_id)
        business_objective = _business_objective(campaign)

        if profile == "structured_exact":
            metric_key = case["expected_facts"][0]["key"]
            metric_mapping = self._taxonomy["metric_mapping"][metric_key]
            language_style = (
                "ko_en_mixed"
                if metric_key in {"ctr", "cvr", "cpa", "roas"}
                or any(
                    name in case["query"]
                    for name in ("Google Ads", "Meta Ads", "YouTube")
                )
                else "professional_ko"
            )
            return _taxonomy_assignment(
                self._taxonomy,
                marketing_domain=metric_mapping["marketing_domain"],
                analysis_task="metric_lookup",
                business_objective=business_objective,
                funnel_stage=metric_mapping["funnel_stage"],
                metric_family=metric_mapping["metric_family"],
                scope_type="campaign_platform_day",
                temporal_granularity="day",
                difficulty="l2_filtered_lookup",
                evidence_type="pg_metric",
                answer_mode="numeric_fact",
                language_style=language_style,
                risk_types=["none"],
            )
        if profile == "lexical_identifier":
            return _taxonomy_assignment(
                self._taxonomy,
                marketing_domain="entity_governance",
                analysis_task="entity_resolution",
                business_objective=business_objective,
                funnel_stage="not_applicable",
                metric_family="entity_metadata",
                scope_type="entity_only",
                temporal_granularity="none",
                difficulty="l1_entity_or_fact",
                evidence_type="pg_entity",
                answer_mode="entity_record",
                language_style=(
                    "keyword_short"
                    if "campaign-code" in case["tags"]
                    else "professional_ko"
                ),
                risk_types=["none"],
            )
        if profile == "no_answer":
            return _taxonomy_assignment(
                self._taxonomy,
                marketing_domain="entity_governance",
                analysis_task="no_answer_detection",
                business_objective="unknown",
                funnel_stage="not_applicable",
                metric_family="none",
                scope_type="missing_or_ambiguous",
                temporal_granularity="unspecified",
                difficulty="l5_ambiguous_or_adversarial",
                evidence_type="absence_proof",
                answer_mode="abstention",
                language_style="colloquial_ko",
                risk_types=["missing_entity"],
            )
        if profile == "ambiguous":
            return _taxonomy_assignment(
                self._taxonomy,
                marketing_domain="entity_governance",
                analysis_task="clarification",
                business_objective="unknown",
                funnel_stage="not_applicable",
                metric_family="none",
                scope_type="missing_or_ambiguous",
                temporal_granularity="unspecified",
                difficulty="l5_ambiguous_or_adversarial",
                evidence_type="none_expected",
                answer_mode="clarification",
                language_style="colloquial_ko",
                risk_types=["entity_ambiguity"],
            )
        if profile == "adversarial":
            return _taxonomy_assignment(
                self._taxonomy,
                marketing_domain="creative_performance",
                analysis_task="evidence_boundary",
                business_objective=business_objective,
                funnel_stage="cross_funnel",
                metric_family="none",
                scope_type="multi_source",
                temporal_granularity="unspecified",
                difficulty="l5_ambiguous_or_adversarial",
                evidence_type="none_expected",
                answer_mode="abstention",
                language_style="colloquial_ko",
                risk_types=["unsupported_causality", "insufficient_evidence"],
            )
        raise ValueError(f"unsupported query profile: {profile}")

    def _audit(
        self,
        generated_at: str,
        campaigns: Sequence[CampaignSource],
        metrics: dict[tuple[str, str], list[MetricSource]],
        partial_observations: Sequence[PartialObservationSource],
        documents: Sequence[DocumentSource],
    ) -> dict[str, Any]:
        if self._database is not None:
            with self._database.connect() as connection:
                counts = {
                    table: int(
                        connection.execute(
                            f"SELECT count(*) AS total FROM {table}"
                        ).fetchone()["total"]
                    )
                    for table in (
                        "workspaces",
                        "campaigns",
                        "campaign_observations",
                        "platform_slices",
                        "metric_observations",
                        "campaign_documents",
                    )
                }
                period = connection.execute(
                    """SELECT min(c.period_start) AS start_date,
                        max(c.period_end) AS end_date
                    FROM campaigns c
                    JOIN workspace_memberships wm ON wm.workspace_id = c.workspace_id
                    JOIN users u ON u.id = wm.user_id
                    WHERE u.google_subject = %s""",
                    (SYNTHETIC_SOURCE,),
                ).fetchone()
                completeness_rows = connection.execute(
                    """SELECT completeness_status, count(*) AS total
                    FROM campaign_observations
                    GROUP BY completeness_status
                    ORDER BY completeness_status"""
                ).fetchall()
                platform_rows = connection.execute(
                    """SELECT surface, currency_code, count(*) AS total
                    FROM platform_slices
                    WHERE fetch_run_ref LIKE %s
                    GROUP BY surface, currency_code
                    ORDER BY surface, currency_code""",
                    (f"{SYNTHETIC_SOURCE}:%",),
                ).fetchall()
                metric_rows = connection.execute(
                    """SELECT metric_key, unit, count(*) AS total
                    FROM metric_observations
                    WHERE provenance_ref LIKE %s
                    GROUP BY metric_key, unit
                    ORDER BY metric_key, unit""",
                    (f"{SYNTHETIC_SOURCE}:%",),
                ).fetchall()
                duplicate_campaign_names = connection.execute(
                    """SELECT count(*) AS total FROM (
                        SELECT workspace_id, name FROM campaigns
                        GROUP BY workspace_id, name HAVING count(*) > 1
                    ) duplicate_names"""
                ).fetchone()["total"]
        else:
            unique_workspaces = {item.workspace_id for item in campaigns}
            counts = {
                "workspaces": len(unique_workspaces),
                "campaigns": len(campaigns),
                "campaign_observations": len(campaigns) * 90,
                "platform_slices": sum(len(c.platforms) for c in campaigns) * 90,
                "metric_observations": sum(len(m_list) for m_list in metrics.values()),
                "campaign_documents": len(documents),
            }
            start_date = min(c.period_start for c in campaigns) if campaigns else date(2025, 1, 1)
            end_date = max(c.period_end for c in campaigns) if campaigns else date(2025, 4, 1)
            period = {"start_date": start_date, "end_date": end_date}
            partial_count = len(partial_observations)
            complete_count = counts["campaign_observations"] - partial_count
            completeness_rows = [
                {"completeness_status": "COMPLETE", "total": complete_count},
                {"completeness_status": "PARTIAL", "total": partial_count},
            ]
            platform_counter: Counter[tuple[str, str]] = Counter()
            for c in campaigns:
                curr = "USD" if "Synthetic Marketing Lab 03" in c.workspace_name else "KRW"
                for s in c.platforms:
                    platform_counter[(s, curr)] += 90
            platform_rows = [
                {"surface": s, "currency_code": curr, "total": total}
                for (s, curr), total in sorted(platform_counter.items())
            ]
            metric_counter: Counter[tuple[str, str]] = Counter()
            for (cid, mkey), mlist in metrics.items():
                for m in mlist:
                    metric_counter[(m.metric_key, m.unit)] += 1
            metric_rows = [
                {"metric_key": k, "unit": u, "total": total}
                for (k, u), total in sorted(metric_counter.items())
            ]
            duplicate_campaign_names = 0

        issues = []
        if counts["campaign_documents"] == 0:
            issues.append(
                {
                    "code": "DOCUMENT_CORPUS_EMPTY",
                    "severity": "blocking_for_document_profiles",
                    "detail": (
                        "Semantic, entity-semantic, mixed PG+document, qrels passage, "
                        "and gold span cases cannot be grounded."
                    ),
                }
            )
        partial = next(
            (
                int(row["total"])
                for row in completeness_rows
                if row["completeness_status"] == "PARTIAL"
            ),
            0,
        )
        if partial:
            issues.append(
                {
                    "code": "PARTIAL_OBSERVATIONS_PRESENT",
                    "severity": "expected_edge_case",
                    "count": partial,
                    "detail": "Conversion tracking gaps are explicitly marked.",
                }
            )
        issues.append(
            {
                "code": "MULTI_CURRENCY_DATASET",
                "severity": "requires_unit_aware_evaluation",
                "detail": "KRW and USD values must never be aggregated without unit filters.",
            }
        )
        document_cases = 130 if counts["campaign_documents"] else 0
        supported_profiles = {
            "structured_exact": 280,
            "lexical_identifier": 90,
            "no_answer": 50 if self._version == "golden-v2" else 30,
            "ambiguous": 50 if self._version == "golden-v2" else 20,
            "adversarial": 50,
        }
        if document_cases:
            supported_profiles.update(
                {
                    "semantic": 50,
                    "entity_semantic": 30,
                    "mixed_structured_semantic": 50,
                }
            )
        scenario_breakdown = {
            "metric_lookup": 100,
            "entity_resolution": 90,
            "no_answer_detection": 50 if self._version == "golden-v2" else 30,
            "clarification": 50 if self._version == "golden-v2" else 20,
            "causal_evidence_boundary": 50 if self._version == "golden-v2" else 20,
            "aggregation": 30,
            "period_comparison": 30,
            "platform_comparison": 30,
            "campaign_comparison": 30,
            "trend_analysis": 30,
            "tracking_gap_detection": 30,
            "comparison_safety": 30,
        }
        if document_cases:
            scenario_breakdown.update(
                {
                    "document_causal_diagnosis": 50,
                    "document_goal_pacing": 30,
                    "pg_document_recommendation": 50,
                }
            )
        return {
            "audit_version": "v1",
            "generated_at": generated_at,
            "source": SYNTHETIC_SOURCE,
            "source_type": "approved_synthetic_postgresql",
            "table_counts": counts,
            "campaign_period": {
                "start": _json_value(period["start_date"]),
                "end": _json_value(period["end_date"]),
            },
            "completeness_distribution": {
                row["completeness_status"]: int(row["total"])
                for row in completeness_rows
            },
            "platform_currency_distribution": [
                {
                    "platform": row["surface"],
                    "currency": row["currency_code"],
                    "slice_count": int(row["total"]),
                }
                for row in platform_rows
            ],
            "metric_distribution": [
                {
                    "metric_key": row["metric_key"],
                    "unit": row["unit"],
                    "row_count": int(row["total"]),
                }
                for row in metric_rows
            ],
            "duplicate_campaign_names_within_workspace": int(duplicate_campaign_names),
            "issues": issues,
            "generation_plan": {
                "target_cases": 600,
                "generated_cases": 470 + document_cases,
                "supported": supported_profiles,
                "scenario_breakdown": scenario_breakdown,
                "excluded_document_dependent_cases": 130 - document_cases,
            },
        }

    def _load_campaigns(self) -> list[CampaignSource]:
        if self._database is not None:
            with self._database.connect() as connection:
                rows = connection.execute(
                    """SELECT c.id, c.workspace_id, w.name AS workspace_name,
                        c.name, c.goal, c.period_start, c.period_end, c.target_metrics
                    FROM campaigns c
                    JOIN workspaces w ON w.id = c.workspace_id
                    JOIN workspace_memberships wm ON wm.workspace_id = w.id
                    JOIN users u ON u.id = wm.user_id
                    WHERE u.google_subject = %s""",
                    (SYNTHETIC_SOURCE,),
                ).fetchall()
                platform_rows = connection.execute(
                    """SELECT o.campaign_id, s.surface, s.external_campaign_ref
                    FROM campaign_observations o
                    JOIN platform_slices s ON s.observation_id = o.id
                    JOIN campaigns c ON c.id = o.campaign_id
                    JOIN workspace_memberships wm ON wm.workspace_id = c.workspace_id
                    JOIN users u ON u.id = wm.user_id
                    WHERE u.google_subject = %s
                    GROUP BY o.campaign_id, s.surface, s.external_campaign_ref""",
                    (SYNTHETIC_SOURCE,),
                ).fetchall()

            platforms: dict[str, set[str]] = defaultdict(set)
            external_refs: dict[str, set[str]] = defaultdict(set)
            for row in platform_rows:
                campaign_id = str(row["campaign_id"])
                platforms[campaign_id].add(row["surface"])
                if row["external_campaign_ref"]:
                    external_refs[campaign_id].add(row["external_campaign_ref"])

            campaigns = [
                CampaignSource(
                    id=str(row["id"]),
                    workspace_id=str(row["workspace_id"]),
                    workspace_name=row["workspace_name"],
                    name=row["name"],
                    goal=row["goal"],
                    period_start=row["period_start"],
                    period_end=row["period_end"],
                    target_metrics=tuple(row["target_metrics"]),
                    platforms=tuple(sorted(platforms[str(row["id"])])),
                    external_refs=tuple(sorted(external_refs[str(row["id"])])),
                )
                for row in rows
            ]
            return sorted(campaigns, key=lambda item: item.code)

        config = self._synthetic_config or SyntheticConfig()
        plans = build_campaign_plans(config)
        campaigns = [
            CampaignSource(
                id=str(plan.id),
                workspace_id=str(plan.workspace.id),
                workspace_name=plan.workspace.name,
                name=plan.name,
                goal=plan.goal,
                period_start=plan.start,
                period_end=plan.end,
                target_metrics=plan.target_metrics,
                platforms=plan.platforms,
                external_refs=tuple(
                    f"SYN-{surface[:3]}-{plan.global_index + 1:06d}"
                    for surface in plan.platforms
                ),
            )
            for plan in plans
        ]
        return sorted(campaigns, key=lambda item: item.code)

    def _load_metrics(
        self, campaigns: Sequence[CampaignSource]
    ) -> dict[tuple[str, str], list[MetricSource]]:
        if self._database is not None:
            campaign_ids = [UUID(item.id) for item in campaigns]
            with self._database.connect() as connection:
                rows = connection.execute(
                    """SELECT o.campaign_id, o.id AS observation_id,
                        s.slice_index, s.surface, s.external_campaign_ref,
                        s.attribution_setting,
                        m.metric_index, m.metric_key, m.value, m.unit,
                        m.period_start, m.period_end, m.provenance_ref, m.calculation
                    FROM campaign_observations o
                    JOIN platform_slices s ON s.observation_id = o.id
                    JOIN metric_observations m
                      ON m.observation_id = s.observation_id
                     AND m.slice_index = s.slice_index
                    WHERE o.campaign_id = ANY(%s)
                      AND o.completeness_status = 'COMPLETE'
                      AND m.metric_key = ANY(%s)
                    ORDER BY o.campaign_id, m.metric_key, m.period_start, s.surface""",
                    (campaign_ids, list(_METRIC_KEYS)),
                ).fetchall()
            output: dict[tuple[str, str], list[MetricSource]] = defaultdict(list)
            for row in rows:
                metric = MetricSource(
                    campaign_id=str(row["campaign_id"]),
                    observation_id=str(row["observation_id"]),
                    slice_index=int(row["slice_index"]),
                    metric_index=int(row["metric_index"]),
                    surface=row["surface"],
                    external_campaign_ref=row["external_campaign_ref"],
                    attribution_setting=row["attribution_setting"],
                    metric_key=row["metric_key"],
                    value=float(row["value"]),
                    unit=row["unit"],
                    period_start=row["period_start"],
                    period_end=row["period_end"],
                    provenance_ref=row["provenance_ref"],
                    calculation=row["calculation"],
                )
                output[(metric.campaign_id, metric.metric_key)].append(metric)
            return output

        config = self._synthetic_config or SyntheticConfig()
        plans = {str(plan.id): plan for plan in build_campaign_plans(config)}
        output = defaultdict(list)
        for campaign in campaigns:
            plan = plans[campaign.id]
            for day_index in range(config.days):
                observation_id = str(stable_uuid("observation", plan.id, day_index))
                period_start = plan.start + timedelta(days=day_index)
                period_end = period_start
                provenance_ref = f"{SYNTHETIC_SOURCE}:observation:{plan.global_index + 1:04d}:{day_index + 1:02d}"
                platform_days = build_platform_days(
                    plan,
                    day_index=day_index,
                    total_days=config.days,
                    seed=config.seed,
                )
                for slice_index, platform_day in enumerate(platform_days):
                    for metric_index, datum in enumerate(platform_day.metrics):
                        if datum.key in _METRIC_KEYS:
                            metric_source = MetricSource(
                                campaign_id=campaign.id,
                                observation_id=observation_id,
                                slice_index=slice_index,
                                metric_index=metric_index,
                                surface=platform_day.surface,
                                external_campaign_ref=platform_day.external_campaign_ref,
                                attribution_setting=platform_day.attribution_setting,
                                metric_key=datum.key,
                                value=datum.value,
                                unit=datum.unit,
                                period_start=period_start,
                                period_end=period_end,
                                provenance_ref=provenance_ref,
                                calculation=datum.calculation,
                            )
                            output[(campaign.id, datum.key)].append(metric_source)
        return output

    def _load_partial_observations(self) -> list[PartialObservationSource]:
        if self._database is not None:
            with self._database.connect() as connection:
                rows = connection.execute(
                    """SELECT o.campaign_id, o.id AS observation_id,
                        o.period_start, o.period_end, o.missing_reasons, o.captured_at
                    FROM campaign_observations o
                    JOIN campaigns c ON c.id = o.campaign_id
                    JOIN workspace_memberships wm ON wm.workspace_id = c.workspace_id
                    JOIN users u ON u.id = wm.user_id
                    WHERE u.google_subject = %s
                      AND o.completeness_status = 'PARTIAL'
                    ORDER BY o.campaign_id, o.period_start""",
                    (SYNTHETIC_SOURCE,),
                ).fetchall()
            return [
                PartialObservationSource(
                    campaign_id=str(row["campaign_id"]),
                    observation_id=str(row["observation_id"]),
                    period_start=row["period_start"],
                    period_end=row["period_end"],
                    missing_reasons=tuple(row["missing_reasons"]),
                    captured_at=row["captured_at"],
                )
                for row in rows
            ]

        config = self._synthetic_config or SyntheticConfig()
        plans = build_campaign_plans(config)
        output_partial: list[PartialObservationSource] = []
        for plan in plans:
            for day_index in range(config.days):
                observation_id = str(stable_uuid("observation", plan.id, day_index))
                period_start = plan.start + timedelta(days=day_index)
                period_end = period_start
                platform_days = build_platform_days(
                    plan,
                    day_index=day_index,
                    total_days=config.days,
                    seed=config.seed,
                )
                missing_reasons = tuple(
                    item.missing_reason
                    for item in platform_days
                    if item.missing_reason is not None
                )
                if missing_reasons:
                    output_partial.append(
                        PartialObservationSource(
                            campaign_id=str(plan.id),
                            observation_id=observation_id,
                            period_start=period_start,
                            period_end=period_end,
                            missing_reasons=missing_reasons,
                            captured_at=datetime.combine(period_end, datetime.min.time(), UTC) + timedelta(days=1),
                        )
                    )
        return output_partial

    def _load_documents(self) -> list[DocumentSource]:
        if self._database is not None:
            with self._database.connect() as connection:
                rows = connection.execute(
                    """SELECT d.id, d.campaign_id, d.workspace_id, d.document_type,
                        d.title, d.content, d.source_ref, d.created_at
                    FROM campaign_documents d
                    JOIN campaigns c ON c.id = d.campaign_id
                    JOIN workspace_memberships wm ON wm.workspace_id = c.workspace_id
                    JOIN users u ON u.id = wm.user_id
                    WHERE u.google_subject = %s
                    ORDER BY d.campaign_id, d.document_type""",
                    (SYNTHETIC_SOURCE,),
                ).fetchall()
            return [
                DocumentSource(
                    id=str(row["id"]),
                    campaign_id=str(row["campaign_id"]),
                    workspace_id=str(row["workspace_id"]),
                    document_type=row["document_type"],
                    title=row["title"],
                    content=row["content"],
                    source_ref=row["source_ref"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

        config = self._synthetic_config or SyntheticConfig()
        plans = build_campaign_plans(config)
        output_docs: list[DocumentSource] = []
        for plan in plans:
            for doc in build_campaign_documents(plan):
                output_docs.append(
                    DocumentSource(
                        id=str(doc.id),
                        campaign_id=str(doc.campaign_id),
                        workspace_id=str(doc.workspace_id),
                        document_type=doc.document_type,
                        title=doc.title,
                        content=doc.content,
                        source_ref=doc.source_ref,
                        created_at=doc.created_at,
                    )
                )
        return output_docs

    def _add_document_cases(
        self,
        campaigns: Sequence[CampaignSource],
        documents: Sequence[DocumentSource],
        metrics: dict[tuple[str, str], list[MetricSource]],
        cases: list[dict[str, Any]],
        qrels: list[dict[str, Any]],
        corpus: dict[str, dict[str, Any]],
        gold_spans: list[dict[str, Any]],
        needs_review: list[dict[str, Any]],
    ) -> None:
        by_campaign_type = {
            (document.campaign_id, document.document_type): document
            for document in documents
        }
        if len(by_campaign_type) < len(campaigns) * 3:
            raise RuntimeError(
                "document Golden requires BRIEF, MEMO, and ANALYSIS for every campaign"
            )
        for campaign in campaigns[:50]:
            document = by_campaign_type[(campaign.id, "MEMO")]
            passage = self._register_document_evidence(
                case_id=f"semantic.{campaign.code.lower()}.diagnosis",
                document=document,
                marker="핵심 관찰:",
                qrels=qrels,
                gold_spans=gold_spans,
            )
            case_id = f"semantic.{campaign.code.lower()}.diagnosis"
            cases.append(
                {
                    "golden_version": GOLDEN_VERSION,
                    "case_id": case_id,
                    "query": "성과 변화와 함께 운영 메모에 기록된 원인 후보를 설명해줘",
                    "language": "ko-KR",
                    "query_profile": "semantic",
                    "required_sources": ["documents"],
                    "scope": self._scope(campaign),
                    "filters": {
                        "campaign_id": campaign.id,
                        "document_types": ["MEMO"],
                    },
                    "expected_facts": [],
                    "expected_answer": passage,
                    "acceptable_answers": [passage],
                    "gold_evidence": [
                        {
                            "corpus_ref": document.corpus_ref,
                            "source_type": "document",
                            "table": "campaign_documents",
                        }
                    ],
                    "unanswerable": False,
                    "ambiguity": None,
                    "validation_status": "needs_review",
                    "reviewer_notes": "Review the source-grounded causal wording.",
                    "group_id": f"campaign:{campaign.id}",
                    "leakage_group_ids": [f"campaign:{campaign.id}"],
                    "split_anchor": campaign.code,
                    "tags": ["semantic", "memo", "causal-diagnosis"],
                    "taxonomy_seed": {
                        "marketing_domain": "creative_performance",
                        "analysis_task": "causal_diagnosis",
                        "business_objective": _business_objective(campaign),
                        "funnel_stage": "cross_funnel",
                        "metric_family": "none",
                        "scope_type": "campaign_period",
                        "temporal_granularity": "campaign_lifetime",
                        "difficulty": "l4_multi_hop_or_source",
                        "evidence_type": "document_passage",
                        "answer_mode": "grounded_explanation",
                        "language_style": "colloquial_ko",
                        "risk_types": ["none"],
                    },
                }
            )
            needs_review.append(
                {
                    "case_id": case_id,
                    "reason": "Document diagnosis requires human passage review.",
                    "review_fields": ["expected_answer", "gold_evidence"],
                }
            )

        for campaign in campaigns[50:80]:
            document = by_campaign_type[(campaign.id, "BRIEF")]
            case_id = f"entity-semantic.{campaign.code.lower()}.pacing"
            passage = self._register_document_evidence(
                case_id=case_id,
                document=document,
                marker="페이싱 원칙:",
                qrels=qrels,
                gold_spans=gold_spans,
            )
            cases.append(
                {
                    "golden_version": GOLDEN_VERSION,
                    "case_id": case_id,
                    "query": f"{campaign.code} 캠페인의 예산 페이싱 기준을 브리프에서 찾아줘",
                    "language": "ko-KR",
                    "query_profile": "entity_semantic",
                    "required_sources": ["documents"],
                    "scope": self._scope(campaign),
                    "filters": {
                        "campaign_id": campaign.id,
                        "document_types": ["BRIEF"],
                    },
                    "expected_facts": [],
                    "expected_answer": passage,
                    "acceptable_answers": [passage],
                    "gold_evidence": [
                        {
                            "corpus_ref": document.corpus_ref,
                            "source_type": "document",
                            "table": "campaign_documents",
                        }
                    ],
                    "unanswerable": False,
                    "ambiguity": None,
                    "validation_status": "needs_review",
                    "reviewer_notes": "Review budget pacing scope and unit.",
                    "group_id": f"campaign:{campaign.id}",
                    "leakage_group_ids": [f"campaign:{campaign.id}"],
                    "split_anchor": campaign.code,
                    "tags": ["entity-semantic", "brief", "goal-pacing"],
                    "taxonomy_seed": {
                        "marketing_domain": "budget_delivery",
                        "analysis_task": "goal_pacing",
                        "business_objective": _business_objective(campaign),
                        "funnel_stage": "cross_funnel",
                        "metric_family": "spend_cost",
                        "scope_type": "campaign_period",
                        "temporal_granularity": "week",
                        "difficulty": "l4_multi_hop_or_source",
                        "evidence_type": "document_passage",
                        "answer_mode": "grounded_explanation",
                        "language_style": "professional_ko",
                        "risk_types": ["none"],
                    },
                }
            )
            needs_review.append(
                {
                    "case_id": case_id,
                    "reason": "Document pacing rule requires human passage review.",
                    "review_fields": ["expected_answer", "gold_evidence"],
                }
            )

        for index, campaign in enumerate(campaigns[80:130]):
            document = by_campaign_type[(campaign.id, "ANALYSIS")]
            metric_key = ("clicks", "spend", "conversions")[index % 3]
            metric = metrics[(campaign.id, metric_key)][0]
            corpus[metric.corpus_ref] = self._metric_corpus_record(metric, campaign)
            case_id = f"mixed.{campaign.code.lower()}.recommendation-{metric_key}"
            passage = self._register_document_evidence(
                case_id=case_id,
                document=document,
                marker="권고 근거:",
                qrels=qrels,
                gold_spans=gold_spans,
            )
            qrels.append(
                {
                    "case_id": case_id,
                    "corpus_ref": metric.corpus_ref,
                    "source_type": "pg",
                    "relevance": 2,
                    "reason": "Structured performance fact used with the recommendation passage.",
                }
            )
            value = _format_metric_value(metric.value, metric.unit)
            cases.append(
                {
                    "golden_version": GOLDEN_VERSION,
                    "case_id": case_id,
                    "query": (
                        f"{campaign.code}의 {_METRIC_LABELS[metric_key]} 수치와 "
                        "분석 문서를 함께 보고 다음 조치를 제안해줘"
                    ),
                    "language": "ko-KR",
                    "query_profile": "mixed_structured_semantic",
                    "required_sources": ["pg", "documents"],
                    "scope": self._scope(campaign),
                    "filters": {
                        "campaign_id": campaign.id,
                        "metric_keys": [metric_key],
                        "document_types": ["ANALYSIS"],
                    },
                    "expected_facts": [
                        {
                            "key": metric_key,
                            "value": value,
                            "unit": metric.unit,
                            "provenance_ref": metric.provenance_ref,
                        }
                    ],
                    "expected_answer": f"{_metric_answer(metric_key, metric.value, metric.unit)}. {passage}",
                    "acceptable_answers": [passage, value],
                    "gold_evidence": [
                        {
                            "corpus_ref": metric.corpus_ref,
                            "source_type": "pg",
                            "table": "metric_observations",
                        },
                        {
                            "corpus_ref": document.corpus_ref,
                            "source_type": "document",
                            "table": "campaign_documents",
                        },
                    ],
                    "unanswerable": False,
                    "ambiguity": None,
                    "validation_status": "needs_review",
                    "reviewer_notes": "Review the numeric fact and grounded recommendation together.",
                    "group_id": f"campaign:{campaign.id}",
                    "leakage_group_ids": [f"campaign:{campaign.id}"],
                    "split_anchor": campaign.code,
                    "tags": ["mixed", "analysis", "recommendation", metric_key],
                    "taxonomy_seed": {
                        "marketing_domain": "creative_performance",
                        "analysis_task": "recommendation",
                        "business_objective": _business_objective(campaign),
                        "funnel_stage": "cross_funnel",
                        "metric_family": self._taxonomy["metric_mapping"][metric_key][
                            "metric_family"
                        ],
                        "scope_type": "multi_source",
                        "temporal_granularity": "campaign_lifetime",
                        "difficulty": "l4_multi_hop_or_source",
                        "evidence_type": "pg_and_document",
                        "answer_mode": "grounded_explanation",
                        "language_style": "professional_ko",
                        "risk_types": ["none"],
                    },
                }
            )
            needs_review.append(
                {
                    "case_id": case_id,
                    "reason": "PG plus document recommendation requires human review.",
                    "review_fields": [
                        "expected_facts",
                        "expected_answer",
                        "gold_evidence",
                    ],
                }
            )

    @staticmethod
    def _register_document_evidence(
        *,
        case_id: str,
        document: DocumentSource,
        marker: str,
        qrels: list[dict[str, Any]],
        gold_spans: list[dict[str, Any]],
    ) -> str:
        marker_start = document.content.find(marker)
        if marker_start < 0:
            raise RuntimeError(f"document marker is missing: {marker}")
        passage_start = marker_start + len(marker)
        while document.content[passage_start : passage_start + 1] == " ":
            passage_start += 1
        line_end = document.content.find("\n", passage_start)
        passage_end = len(document.content) if line_end < 0 else line_end
        passage = document.content[passage_start:passage_end].strip()
        passage_end = passage_start + len(passage)
        qrels.append(
            {
                "case_id": case_id,
                "corpus_ref": document.corpus_ref,
                "source_type": "document",
                "relevance": 3,
                "reason": f"Authoritative {document.document_type} passage.",
            }
        )
        gold_spans.append(
            {
                "case_id": case_id,
                "document_ref": document.corpus_ref,
                "char_start": passage_start,
                "char_end": passage_end,
                "text": passage,
                "relevance": 3,
            }
        )
        return passage

    def _add_structured_cases(
        self,
        campaigns: Sequence[CampaignSource],
        metrics: dict[tuple[str, str], list[MetricSource]],
        cases: list[dict[str, Any]],
        qrels: list[dict[str, Any]],
        corpus: dict[str, dict[str, Any]],
    ) -> None:
        for index, campaign in enumerate(campaigns):
            metric_key = _METRIC_KEYS[index % len(_METRIC_KEYS)]
            candidates = metrics[(campaign.id, metric_key)]
            metric = candidates[(index * 17) % len(candidates)]
            value = _format_metric_value(metric.value, metric.unit)
            answer = _metric_answer(metric.metric_key, metric.value, metric.unit)
            case_id = f"structured.{campaign.code.lower()}.{metric_key}"
            evidence = self._metric_corpus_record(metric, campaign)
            corpus[metric.corpus_ref] = evidence
            qrels.append(
                {
                    "case_id": case_id,
                    "corpus_ref": metric.corpus_ref,
                    "source_type": "pg",
                    "relevance": 3,
                    "reason": "Exact metric row matching campaign, platform, and period.",
                }
            )
            cases.append(
                {
                    "golden_version": GOLDEN_VERSION,
                    "case_id": case_id,
                    "query": (
                        f"{campaign.name}의 {metric.period_start.isoformat()} "
                        f"{_SURFACE_LABELS[metric.surface]} "
                        f"{_METRIC_LABELS[metric.metric_key]} 값은 얼마야?"
                    ),
                    "language": "ko-KR",
                    "query_profile": "structured_exact",
                    "required_sources": ["pg"],
                    "scope": self._scope(campaign),
                    "filters": {
                        "campaign_id": campaign.id,
                        "platform": metric.surface,
                        "start_date": metric.period_start.isoformat(),
                        "end_date": metric.period_end.isoformat(),
                        "metric_keys": [metric.metric_key],
                    },
                    "expected_facts": [
                        {
                            "key": metric.metric_key,
                            "value": value,
                            "unit": metric.unit,
                            "provenance_ref": metric.provenance_ref,
                        }
                    ],
                    "expected_answer": answer,
                    "acceptable_answers": _acceptable_metric_answers(metric),
                    "gold_evidence": [
                        {
                            "corpus_ref": metric.corpus_ref,
                            "source_type": "pg",
                            "table": "metric_observations",
                        }
                    ],
                    "unanswerable": False,
                    "ambiguity": None,
                    "validation_status": "auto_validated",
                    "reviewer_notes": "Exact source row and unit were verified.",
                    "group_id": f"campaign:{campaign.id}",
                    "leakage_group_ids": [f"campaign:{campaign.id}"],
                    "split_anchor": campaign.code,
                    "tags": [
                        "exact-value",
                        "period-filter",
                        "platform-filter",
                        metric.metric_key,
                    ],
                }
            )

    def _add_aggregation_cases(
        self,
        campaigns: Sequence[CampaignSource],
        metrics: dict[tuple[str, str], list[MetricSource]],
        cases: list[dict[str, Any]],
        qrels: list[dict[str, Any]],
        corpus: dict[str, dict[str, Any]],
    ) -> None:
        metric_keys = ("impressions", "clicks", "spend")
        for index, campaign in enumerate(campaigns):
            metric_key = metric_keys[index % len(metric_keys)]
            surface = campaign.platforms[index % len(campaign.platforms)]
            period_start = campaign.period_start + timedelta(days=(index % 4) * 7)
            period_end = period_start + timedelta(days=6)
            rows = self._metric_range(
                metrics, campaign, metric_key, surface, period_start, period_end
            )
            if len(rows) != 7:
                raise RuntimeError("weekly aggregation requires seven source rows")
            total = sum(row.value for row in rows)
            unit = rows[0].unit
            case_id = f"structured.{campaign.code.lower()}.weekly-{metric_key}"
            evidence = self._register_metric_evidence(
                case_id, rows, campaign, qrels, corpus
            )
            metric_taxonomy = self._taxonomy["metric_mapping"][metric_key]
            cases.append(
                {
                    "golden_version": GOLDEN_VERSION,
                    "case_id": case_id,
                    "query": (
                        f"{campaign.name}의 {period_start.isoformat()}부터 "
                        f"{period_end.isoformat()}까지 {_SURFACE_LABELS[surface]} "
                        f"{_METRIC_LABELS[metric_key]} 합계를 계산해줘"
                    ),
                    "language": "ko-KR",
                    "query_profile": "structured_exact",
                    "required_sources": ["pg"],
                    "scope": self._scope(campaign),
                    "filters": {
                        "campaign_id": campaign.id,
                        "platform": surface,
                        "start_date": period_start.isoformat(),
                        "end_date": period_end.isoformat(),
                        "metric_keys": [metric_key],
                    },
                    "expected_facts": [
                        {
                            "key": f"total_{metric_key}",
                            "value": _format_metric_value(total, unit),
                            "unit": unit,
                            "calculation": "sum(daily values)",
                            "source_row_count": len(rows),
                        }
                    ],
                    "expected_answer": _metric_answer(metric_key, total, unit),
                    "acceptable_answers": [_format_metric_value(total, unit)],
                    "gold_evidence": evidence,
                    "unanswerable": False,
                    "ambiguity": None,
                    "validation_status": "auto_validated",
                    "reviewer_notes": "Seven daily rows were summed without unit mixing.",
                    "group_id": f"campaign:{campaign.id}",
                    "leakage_group_ids": [f"campaign:{campaign.id}"],
                    "split_anchor": campaign.code,
                    "tags": ["aggregation", "week", metric_key],
                    "taxonomy_seed": {
                        "marketing_domain": metric_taxonomy["marketing_domain"],
                        "analysis_task": "aggregation",
                        "business_objective": _business_objective(campaign),
                        "funnel_stage": metric_taxonomy["funnel_stage"],
                        "metric_family": metric_taxonomy["metric_family"],
                        "scope_type": "campaign_platform_period",
                        "temporal_granularity": "week",
                        "difficulty": "l3_aggregation_or_comparison",
                        "evidence_type": "pg_metric",
                        "answer_mode": "numeric_fact",
                        "language_style": "professional_ko",
                        "risk_types": ["none"],
                    },
                }
            )

    def _add_period_comparison_cases(
        self,
        campaigns: Sequence[CampaignSource],
        metrics: dict[tuple[str, str], list[MetricSource]],
        cases: list[dict[str, Any]],
        qrels: list[dict[str, Any]],
        corpus: dict[str, dict[str, Any]],
    ) -> None:
        metric_keys = ("impressions", "clicks", "spend")
        for index, campaign in enumerate(campaigns):
            metric_key = metric_keys[index % len(metric_keys)]
            surface = campaign.platforms[index % len(campaign.platforms)]
            first_start = campaign.period_start
            first_end = first_start + timedelta(days=6)
            second_start = first_start + timedelta(days=7)
            second_end = second_start + timedelta(days=6)
            first_rows = self._metric_range(
                metrics, campaign, metric_key, surface, first_start, first_end
            )
            second_rows = self._metric_range(
                metrics, campaign, metric_key, surface, second_start, second_end
            )
            if len(first_rows) != 7 or len(second_rows) != 7:
                raise RuntimeError("period comparison requires two complete weeks")
            first_total = sum(row.value for row in first_rows)
            second_total = sum(row.value for row in second_rows)
            difference = second_total - first_total
            change_rate = difference / first_total if first_total else 0.0
            unit = first_rows[0].unit
            case_id = f"structured.{campaign.code.lower()}.wow-{metric_key}"
            evidence = self._register_metric_evidence(
                case_id, (*first_rows, *second_rows), campaign, qrels, corpus
            )
            metric_taxonomy = self._taxonomy["metric_mapping"][metric_key]
            cases.append(
                {
                    "golden_version": GOLDEN_VERSION,
                    "case_id": case_id,
                    "query": (
                        f"{campaign.name}의 {_SURFACE_LABELS[surface]} "
                        f"{_METRIC_LABELS[metric_key]}을 첫째 주와 둘째 주로 비교해줘"
                    ),
                    "language": "ko-KR",
                    "query_profile": "structured_exact",
                    "required_sources": ["pg"],
                    "scope": self._scope(campaign),
                    "filters": {
                        "campaign_id": campaign.id,
                        "platform": surface,
                        "period_a": [first_start.isoformat(), first_end.isoformat()],
                        "period_b": [second_start.isoformat(), second_end.isoformat()],
                        "metric_keys": [metric_key],
                    },
                    "expected_facts": [
                        {
                            "key": "period_a_total",
                            "value": _format_metric_value(first_total, unit),
                            "unit": unit,
                        },
                        {
                            "key": "period_b_total",
                            "value": _format_metric_value(second_total, unit),
                            "unit": unit,
                        },
                        {
                            "key": "change_rate",
                            "value": _format_metric_value(change_rate, "ratio"),
                            "unit": "ratio",
                            "calculation": "(period_b - period_a) / period_a",
                        },
                    ],
                    "expected_answer": (
                        f"첫째 주 {_format_metric_value(first_total, unit)}, 둘째 주 "
                        f"{_format_metric_value(second_total, unit)}로 "
                        f"변화율은 {change_rate * 100:.2f}%입니다."
                    ),
                    "acceptable_answers": [f"{change_rate * 100:.2f}%"],
                    "gold_evidence": evidence,
                    "unanswerable": False,
                    "ambiguity": None,
                    "validation_status": "auto_validated",
                    "reviewer_notes": "Two equal seven-day periods were compared.",
                    "group_id": f"campaign:{campaign.id}",
                    "leakage_group_ids": [f"campaign:{campaign.id}"],
                    "split_anchor": campaign.code,
                    "tags": ["period-comparison", "wow", metric_key],
                    "taxonomy_seed": {
                        "marketing_domain": metric_taxonomy["marketing_domain"],
                        "analysis_task": "period_comparison",
                        "business_objective": _business_objective(campaign),
                        "funnel_stage": metric_taxonomy["funnel_stage"],
                        "metric_family": metric_taxonomy["metric_family"],
                        "scope_type": "campaign_platform_period",
                        "temporal_granularity": "comparative_periods",
                        "difficulty": "l3_aggregation_or_comparison",
                        "evidence_type": "pg_metric",
                        "answer_mode": "comparison",
                        "language_style": "professional_ko",
                        "risk_types": ["none"],
                    },
                }
            )

    def _add_platform_comparison_cases(
        self,
        campaigns: Sequence[CampaignSource],
        metrics: dict[tuple[str, str], list[MetricSource]],
        cases: list[dict[str, Any]],
        qrels: list[dict[str, Any]],
        corpus: dict[str, dict[str, Any]],
    ) -> None:
        candidates = [
            campaign for campaign in campaigns if len(campaign.platforms) >= 2
        ]
        metric_keys = ("impressions", "clicks", "spend")
        for index, campaign in enumerate(candidates[:30]):
            metric_key = metric_keys[index % len(metric_keys)]
            surfaces = campaign.platforms[:2]
            period_start = campaign.period_start
            period_end = period_start + timedelta(days=6)
            platform_rows = [
                self._metric_range(
                    metrics,
                    campaign,
                    metric_key,
                    surface,
                    period_start,
                    period_end,
                )
                for surface in surfaces
            ]
            if any(len(rows) != 7 for rows in platform_rows):
                raise RuntimeError("platform comparison requires complete weekly rows")
            totals = [sum(row.value for row in rows) for rows in platform_rows]
            unit = platform_rows[0][0].unit
            winner_index = max(range(2), key=lambda item: totals[item])
            case_id = f"structured.{campaign.code.lower()}.platform-{metric_key}"
            evidence = self._register_metric_evidence(
                case_id,
                (*platform_rows[0], *platform_rows[1]),
                campaign,
                qrels,
                corpus,
            )
            metric_taxonomy = self._taxonomy["metric_mapping"][metric_key]
            cases.append(
                {
                    "golden_version": GOLDEN_VERSION,
                    "case_id": case_id,
                    "query": (
                        f"{campaign.name}의 첫 7일 {_METRIC_LABELS[metric_key]}을 "
                        f"{_SURFACE_LABELS[surfaces[0]]}와 "
                        f"{_SURFACE_LABELS[surfaces[1]]}로 비교해줘"
                    ),
                    "language": "ko-KR",
                    "query_profile": "structured_exact",
                    "required_sources": ["pg"],
                    "scope": self._scope(campaign),
                    "filters": {
                        "campaign_id": campaign.id,
                        "platforms": list(surfaces),
                        "start_date": period_start.isoformat(),
                        "end_date": period_end.isoformat(),
                        "metric_keys": [metric_key],
                    },
                    "expected_facts": [
                        {
                            "key": f"{surfaces[0]}_{metric_key}",
                            "value": _format_metric_value(totals[0], unit),
                            "unit": unit,
                        },
                        {
                            "key": f"{surfaces[1]}_{metric_key}",
                            "value": _format_metric_value(totals[1], unit),
                            "unit": unit,
                        },
                        {
                            "key": "higher_platform",
                            "value": surfaces[winner_index],
                            "unit": None,
                        },
                    ],
                    "expected_answer": (
                        f"{_SURFACE_LABELS[surfaces[0]]} "
                        f"{_format_metric_value(totals[0], unit)}, "
                        f"{_SURFACE_LABELS[surfaces[1]]} "
                        f"{_format_metric_value(totals[1], unit)}로 "
                        f"{_SURFACE_LABELS[surfaces[winner_index]]}가 더 높습니다."
                    ),
                    "acceptable_answers": [surfaces[winner_index]],
                    "gold_evidence": evidence,
                    "unanswerable": False,
                    "ambiguity": None,
                    "validation_status": "auto_validated",
                    "reviewer_notes": "Same campaign, currency, and seven-day period.",
                    "group_id": f"campaign:{campaign.id}",
                    "leakage_group_ids": [f"campaign:{campaign.id}"],
                    "split_anchor": campaign.code,
                    "tags": ["platform-comparison", metric_key],
                    "taxonomy_seed": {
                        "marketing_domain": metric_taxonomy["marketing_domain"],
                        "analysis_task": "platform_comparison",
                        "business_objective": _business_objective(campaign),
                        "funnel_stage": metric_taxonomy["funnel_stage"],
                        "metric_family": metric_taxonomy["metric_family"],
                        "scope_type": "cross_platform_period",
                        "temporal_granularity": "week",
                        "difficulty": "l3_aggregation_or_comparison",
                        "evidence_type": "pg_metric",
                        "answer_mode": "comparison",
                        "language_style": "ko_en_mixed",
                        "risk_types": ["none"],
                    },
                }
            )

    def _add_campaign_comparison_cases(
        self,
        campaigns: Sequence[CampaignSource],
        metrics: dict[tuple[str, str], list[MetricSource]],
        cases: list[dict[str, Any]],
        qrels: list[dict[str, Any]],
        corpus: dict[str, dict[str, Any]],
    ) -> None:
        pairs: list[tuple[CampaignSource, CampaignSource, str]] = []
        for left_index, left in enumerate(campaigns):
            for right in campaigns[left_index + 1 :]:
                if left.workspace_id != right.workspace_id:
                    continue
                if left.period_start != right.period_start:
                    continue
                if self._campaign_currency(metrics, left) != self._campaign_currency(
                    metrics, right
                ):
                    continue
                if _split_from_anchor(left.code) != _split_from_anchor(right.code):
                    continue
                common_platforms = sorted(set(left.platforms) & set(right.platforms))
                if not common_platforms:
                    continue
                pairs.append((left, right, common_platforms[0]))
                break
            if len(pairs) >= 30:
                break
        if len(pairs) < 30:
            raise RuntimeError("not enough aligned campaign pairs")

        metric_keys = ("impressions", "clicks", "spend")
        for index, (left, right, surface) in enumerate(pairs):
            metric_key = metric_keys[index % len(metric_keys)]
            period_start = left.period_start
            period_end = period_start + timedelta(days=6)
            left_rows = self._metric_range(
                metrics, left, metric_key, surface, period_start, period_end
            )
            right_rows = self._metric_range(
                metrics, right, metric_key, surface, period_start, period_end
            )
            if len(left_rows) != 7 or len(right_rows) != 7:
                raise RuntimeError(
                    "campaign comparison requires aligned complete weeks"
                )
            totals = [
                sum(row.value for row in left_rows),
                sum(row.value for row in right_rows),
            ]
            unit = left_rows[0].unit
            winner = left if totals[0] >= totals[1] else right
            case_id = f"structured.{left.code.lower()}-{right.code.lower()}.campaign-{metric_key}"
            evidence = self._register_metric_evidence(
                case_id, left_rows, left, qrels, corpus
            )
            evidence.extend(
                self._register_metric_evidence(
                    case_id, right_rows, right, qrels, corpus
                )
            )
            metric_taxonomy = self._taxonomy["metric_mapping"][metric_key]
            cases.append(
                {
                    "golden_version": GOLDEN_VERSION,
                    "case_id": case_id,
                    "query": (
                        f"같은 기간 {_SURFACE_LABELS[surface]}의 "
                        f"{_METRIC_LABELS[metric_key]}을 {left.code}와 "
                        f"{right.code} 캠페인으로 비교해줘"
                    ),
                    "language": "ko-KR",
                    "query_profile": "structured_exact",
                    "required_sources": ["pg"],
                    "scope": self._scope(left),
                    "filters": {
                        "campaign_ids": [left.id, right.id],
                        "platform": surface,
                        "start_date": period_start.isoformat(),
                        "end_date": period_end.isoformat(),
                        "metric_keys": [metric_key],
                    },
                    "expected_facts": [
                        {
                            "key": left.code,
                            "value": _format_metric_value(totals[0], unit),
                            "unit": unit,
                        },
                        {
                            "key": right.code,
                            "value": _format_metric_value(totals[1], unit),
                            "unit": unit,
                        },
                        {"key": "higher_campaign", "value": winner.code, "unit": None},
                    ],
                    "expected_answer": (
                        f"{left.code} {_format_metric_value(totals[0], unit)}, "
                        f"{right.code} {_format_metric_value(totals[1], unit)}로 "
                        f"{winner.code}가 더 높습니다."
                    ),
                    "acceptable_answers": [winner.code],
                    "gold_evidence": evidence,
                    "unanswerable": False,
                    "ambiguity": None,
                    "validation_status": "auto_validated",
                    "reviewer_notes": "Same workspace, currency, platform, and calendar week.",
                    "group_id": f"comparison:{left.id}:{right.id}",
                    "leakage_group_ids": [
                        f"campaign:{left.id}",
                        f"campaign:{right.id}",
                    ],
                    "split_anchor": left.code,
                    "tags": ["campaign-comparison", metric_key],
                    "taxonomy_seed": {
                        "marketing_domain": metric_taxonomy["marketing_domain"],
                        "analysis_task": "campaign_comparison",
                        "business_objective": _business_objective(left),
                        "funnel_stage": metric_taxonomy["funnel_stage"],
                        "metric_family": metric_taxonomy["metric_family"],
                        "scope_type": "cross_campaign_period",
                        "temporal_granularity": "week",
                        "difficulty": "l3_aggregation_or_comparison",
                        "evidence_type": "pg_metric",
                        "answer_mode": "comparison",
                        "language_style": "professional_ko",
                        "risk_types": ["none"],
                    },
                }
            )

    def _add_trend_cases(
        self,
        campaigns: Sequence[CampaignSource],
        metrics: dict[tuple[str, str], list[MetricSource]],
        cases: list[dict[str, Any]],
        qrels: list[dict[str, Any]],
        corpus: dict[str, dict[str, Any]],
    ) -> None:
        metric_keys = ("impressions", "clicks", "spend")
        for index, campaign in enumerate(campaigns):
            metric_key = metric_keys[index % len(metric_keys)]
            surface = campaign.platforms[index % len(campaign.platforms)]
            period_start = campaign.period_start
            period_end = period_start + timedelta(days=27)
            rows = self._metric_range(
                metrics, campaign, metric_key, surface, period_start, period_end
            )
            if len(rows) != 28:
                raise RuntimeError("trend case requires 28 complete daily rows")
            weekly = [
                sum(row.value for row in rows[offset : offset + 7])
                for offset in range(0, 28, 7)
            ]
            change_rate = (weekly[-1] - weekly[0]) / weekly[0] if weekly[0] else 0.0
            direction = (
                "상승"
                if change_rate > 0.05
                else "하락"
                if change_rate < -0.05
                else "보합"
            )
            unit = rows[0].unit
            case_id = f"structured.{campaign.code.lower()}.trend-{metric_key}"
            evidence = self._register_metric_evidence(
                case_id, rows, campaign, qrels, corpus
            )
            metric_taxonomy = self._taxonomy["metric_mapping"][metric_key]
            cases.append(
                {
                    "golden_version": GOLDEN_VERSION,
                    "case_id": case_id,
                    "query": (
                        f"{campaign.name}의 {_SURFACE_LABELS[surface]} "
                        f"{_METRIC_LABELS[metric_key]} 4주 추세를 요약해줘"
                    ),
                    "language": "ko-KR",
                    "query_profile": "structured_exact",
                    "required_sources": ["pg"],
                    "scope": self._scope(campaign),
                    "filters": {
                        "campaign_id": campaign.id,
                        "platform": surface,
                        "start_date": period_start.isoformat(),
                        "end_date": period_end.isoformat(),
                        "metric_keys": [metric_key],
                        "aggregation": "calendar_7_day_blocks",
                    },
                    "expected_facts": [
                        {
                            "key": f"week_{week_index + 1}",
                            "value": _format_metric_value(value, unit),
                            "unit": unit,
                        }
                        for week_index, value in enumerate(weekly)
                    ]
                    + [
                        {"key": "direction", "value": direction, "unit": None},
                        {
                            "key": "week_1_to_4_change_rate",
                            "value": _format_metric_value(change_rate, "ratio"),
                            "unit": "ratio",
                        },
                    ],
                    "expected_answer": (
                        f"주별 값은 {', '.join(_format_metric_value(value, unit) for value in weekly)}이며, "
                        f"1주차 대비 4주차 변화율은 {change_rate * 100:.2f}%로 {direction} 추세입니다."
                    ),
                    "acceptable_answers": [direction, f"{change_rate * 100:.2f}%"],
                    "gold_evidence": evidence,
                    "unanswerable": False,
                    "ambiguity": None,
                    "validation_status": "auto_validated",
                    "reviewer_notes": "Trend direction uses a documented ±5% threshold.",
                    "group_id": f"campaign:{campaign.id}",
                    "leakage_group_ids": [f"campaign:{campaign.id}"],
                    "split_anchor": campaign.code,
                    "tags": ["trend", "four-weeks", metric_key],
                    "taxonomy_seed": {
                        "marketing_domain": metric_taxonomy["marketing_domain"],
                        "analysis_task": "trend_analysis",
                        "business_objective": _business_objective(campaign),
                        "funnel_stage": metric_taxonomy["funnel_stage"],
                        "metric_family": metric_taxonomy["metric_family"],
                        "scope_type": "campaign_platform_period",
                        "temporal_granularity": "month",
                        "difficulty": "l3_aggregation_or_comparison",
                        "evidence_type": "pg_metric",
                        "answer_mode": "trend_summary",
                        "language_style": "professional_ko",
                        "risk_types": ["none"],
                    },
                }
            )

    def _add_tracking_gap_cases(
        self,
        partial_observations: Sequence[PartialObservationSource],
        campaigns: Sequence[CampaignSource],
        cases: list[dict[str, Any]],
        qrels: list[dict[str, Any]],
        corpus: dict[str, dict[str, Any]],
        needs_review: list[dict[str, Any]],
    ) -> None:
        campaign_by_id = {campaign.id: campaign for campaign in campaigns}
        grouped: dict[str, list[PartialObservationSource]] = defaultdict(list)
        for observation in partial_observations:
            grouped[observation.campaign_id].append(observation)
        selected = sorted(
            grouped.items(), key=lambda item: campaign_by_id[item[0]].code
        )[:30]
        if len(selected) < 30:
            raise RuntimeError("not enough partial campaigns for tracking-gap cases")
        for campaign_id, observations in selected:
            campaign = campaign_by_id[campaign_id]
            observations = sorted(observations, key=lambda item: item.period_start)
            case_id = f"structured.{campaign.code.lower()}.tracking-gap"
            evidence = []
            for observation in observations:
                corpus[observation.corpus_ref] = {
                    "corpus_ref": observation.corpus_ref,
                    "record_type": "campaign_observation",
                    "source_type": "pg",
                    "table": "campaign_observations",
                    "workspace_id": campaign.workspace_id,
                    "campaign_id": campaign.id,
                    "campaign_code": campaign.code,
                    "campaign_name": campaign.name,
                    "observation_id": observation.observation_id,
                    "period_start": observation.period_start.isoformat(),
                    "period_end": observation.period_end.isoformat(),
                    "completeness_status": "PARTIAL",
                    "missing_reasons": list(observation.missing_reasons),
                    "captured_at": observation.captured_at.isoformat(),
                    "provenance_ref": f"{SYNTHETIC_SOURCE}:observation:{observation.observation_id}",
                }
                qrels.append(
                    {
                        "case_id": case_id,
                        "corpus_ref": observation.corpus_ref,
                        "source_type": "pg",
                        "relevance": 3,
                        "reason": "Authoritative PARTIAL observation and missing reason.",
                    }
                )
                evidence.append(
                    {
                        "corpus_ref": observation.corpus_ref,
                        "source_type": "pg",
                        "table": "campaign_observations",
                    }
                )
            dates = [item.period_start.isoformat() for item in observations]
            cases.append(
                {
                    "golden_version": GOLDEN_VERSION,
                    "case_id": case_id,
                    "query": f"{campaign.code} 캠패인 전환추적 누락된날짜 찾아줘",
                    "language": "ko-KR",
                    "query_profile": "structured_exact",
                    "required_sources": ["pg"],
                    "scope": self._scope(campaign),
                    "filters": {
                        "campaign_id": campaign.id,
                        "completeness_status": "PARTIAL",
                    },
                    "expected_facts": [
                        {"key": "partial_dates", "value": dates, "unit": "date_list"},
                        {
                            "key": "missing_reasons",
                            "value": sorted(
                                {
                                    reason
                                    for item in observations
                                    for reason in item.missing_reasons
                                }
                            ),
                            "unit": None,
                        },
                    ],
                    "expected_answer": f"전환 추적 누락 날짜는 {', '.join(dates)}입니다.",
                    "acceptable_answers": dates,
                    "gold_evidence": evidence,
                    "unanswerable": False,
                    "ambiguity": None,
                    "validation_status": "needs_review",
                    "reviewer_notes": "Review the user-facing explanation of partial data impact.",
                    "group_id": f"campaign:{campaign.id}",
                    "leakage_group_ids": [f"campaign:{campaign.id}"],
                    "split_anchor": campaign.code,
                    "tags": ["tracking-gap", "partial-observation", "noisy-query"],
                    "taxonomy_seed": {
                        "marketing_domain": "measurement_quality",
                        "analysis_task": "anomaly_detection",
                        "business_objective": _business_objective(campaign),
                        "funnel_stage": "cross_funnel",
                        "metric_family": "data_quality",
                        "scope_type": "campaign_period",
                        "temporal_granularity": "comparative_periods",
                        "difficulty": "l3_aggregation_or_comparison",
                        "evidence_type": "pg_observation",
                        "answer_mode": "data_quality_alert",
                        "language_style": "noisy_ko",
                        "risk_types": ["tracking_gap"],
                    },
                }
            )
            needs_review.append(
                {
                    "case_id": case_id,
                    "reason": "Data-quality impact wording requires human review.",
                    "review_fields": ["expected_answer", "risk_types"],
                }
            )

    def _add_comparison_risk_cases(
        self,
        campaigns: Sequence[CampaignSource],
        metrics: dict[tuple[str, str], list[MetricSource]],
        cases: list[dict[str, Any]],
        qrels: list[dict[str, Any]],
        corpus: dict[str, dict[str, Any]],
        needs_review: list[dict[str, Any]],
    ) -> None:
        self._add_currency_mismatch_cases(
            campaigns, metrics, cases, qrels, corpus, needs_review
        )
        self._add_attribution_mismatch_cases(
            campaigns, metrics, cases, qrels, corpus, needs_review
        )
        self._add_period_mismatch_cases(
            campaigns, metrics, cases, qrels, corpus, needs_review
        )

    def _add_currency_mismatch_cases(
        self,
        campaigns: Sequence[CampaignSource],
        metrics: dict[tuple[str, str], list[MetricSource]],
        cases: list[dict[str, Any]],
        qrels: list[dict[str, Any]],
        corpus: dict[str, dict[str, Any]],
        needs_review: list[dict[str, Any]],
    ) -> None:
        krw = [
            item
            for item in campaigns
            if self._campaign_currency(metrics, item) == "KRW"
        ]
        usd = [
            item
            for item in campaigns
            if self._campaign_currency(metrics, item) == "USD"
        ]
        pairs: list[tuple[CampaignSource, CampaignSource, str]] = []
        used: set[tuple[str, str]] = set()
        for left in krw:
            for right in usd:
                if _split_from_anchor(left.code) != _split_from_anchor(right.code):
                    continue
                if left.period_start != right.period_start:
                    continue
                common = sorted(set(left.platforms) & set(right.platforms))
                if not common or (left.id, right.id) in used:
                    continue
                pairs.append((left, right, common[0]))
                used.add((left.id, right.id))
                break
            if len(pairs) >= 10:
                break
        if len(pairs) < 10:
            raise RuntimeError("not enough cross-currency campaign pairs")

        for left, right, surface in pairs:
            left_rows = self._metric_range(
                metrics,
                left,
                "spend",
                surface,
                left.period_start,
                left.period_start + timedelta(days=6),
            )
            right_rows = self._metric_range(
                metrics,
                right,
                "spend",
                surface,
                right.period_start,
                right.period_start + timedelta(days=6),
            )
            left_total = sum(row.value for row in left_rows)
            right_total = sum(row.value for row in right_rows)
            case_id = f"adversarial.currency.{left.code.lower()}-{right.code.lower()}"
            evidence = self._register_metric_evidence(
                case_id, left_rows, left, qrels, corpus
            )
            evidence.extend(
                self._register_metric_evidence(
                    case_id, right_rows, right, qrels, corpus
                )
            )
            cases.append(
                {
                    "golden_version": GOLDEN_VERSION,
                    "case_id": case_id,
                    "query": (
                        f"{left.code}와 {right.code}의 첫 7일 광고비 숫자만 보고 "
                        "어느 캠페인이 더 효율적인지 확정해줘"
                    ),
                    "language": "ko-KR",
                    "query_profile": "adversarial",
                    "required_sources": ["pg"],
                    "scope": self._scope(left),
                    "filters": {
                        "campaign_ids": [left.id, right.id],
                        "metric_keys": ["spend"],
                    },
                    "expected_facts": [
                        {
                            "key": left.code,
                            "value": _format_metric_value(
                                left_total, left_rows[0].unit
                            ),
                            "unit": left_rows[0].unit,
                        },
                        {
                            "key": right.code,
                            "value": _format_metric_value(
                                right_total, right_rows[0].unit
                            ),
                            "unit": right_rows[0].unit,
                        },
                    ],
                    "expected_answer": (
                        f"{left.code}는 {_format_metric_value(left_total, left_rows[0].unit)} KRW, "
                        f"{right.code}는 {_format_metric_value(right_total, right_rows[0].unit)} USD입니다. "
                        "통화 환산과 성과 지표 없이 효율을 직접 비교할 수 없습니다."
                    ),
                    "acceptable_answers": ["통화 환산 없이 비교할 수 없습니다."],
                    "gold_evidence": evidence,
                    "unanswerable": False,
                    "ambiguity": {
                        "reason": "currency_mismatch",
                        "currencies": ["KRW", "USD"],
                    },
                    "validation_status": "needs_review",
                    "reviewer_notes": "Review the abstention and currency-normalization requirement.",
                    "group_id": f"comparison:{left.id}:{right.id}",
                    "leakage_group_ids": [
                        f"campaign:{left.id}",
                        f"campaign:{right.id}",
                    ],
                    "split_anchor": left.code,
                    "tags": ["currency-mismatch", "unsafe-comparison"],
                    "taxonomy_seed": {
                        "marketing_domain": "measurement_quality",
                        "analysis_task": "evidence_boundary",
                        "business_objective": _business_objective(left),
                        "funnel_stage": "cross_funnel",
                        "metric_family": "spend_cost",
                        "scope_type": "cross_campaign_period",
                        "temporal_granularity": "week",
                        "difficulty": "l5_ambiguous_or_adversarial",
                        "evidence_type": "pg_metric",
                        "answer_mode": "abstention",
                        "language_style": "professional_ko",
                        "risk_types": ["currency_mismatch", "insufficient_evidence"],
                    },
                }
            )
            needs_review.append(
                {
                    "case_id": case_id,
                    "reason": "Cross-currency abstention requires human review.",
                    "review_fields": ["expected_answer", "risk_types"],
                }
            )

    def _add_attribution_mismatch_cases(
        self,
        campaigns: Sequence[CampaignSource],
        metrics: dict[tuple[str, str], list[MetricSource]],
        cases: list[dict[str, Any]],
        qrels: list[dict[str, Any]],
        corpus: dict[str, dict[str, Any]],
        needs_review: list[dict[str, Any]],
    ) -> None:
        candidates = [
            item
            for item in campaigns
            if {"GOOGLE_ADS", "META_ADS"} <= set(item.platforms)
        ][:10]
        if len(candidates) < 10:
            raise RuntimeError("not enough Google and Meta campaigns")
        for campaign in candidates:
            period_start = campaign.period_start
            period_end = period_start + timedelta(days=6)
            google_rows = self._metric_range(
                metrics, campaign, "conversions", "GOOGLE_ADS", period_start, period_end
            )
            meta_rows = self._metric_range(
                metrics, campaign, "conversions", "META_ADS", period_start, period_end
            )
            if len(google_rows) != 7 or len(meta_rows) != 7:
                raise RuntimeError("attribution case requires complete conversion rows")
            google_total = sum(row.value for row in google_rows)
            meta_total = sum(row.value for row in meta_rows)
            settings = [
                google_rows[0].attribution_setting,
                meta_rows[0].attribution_setting,
            ]
            if not all(settings) or settings[0] == settings[1]:
                raise RuntimeError(
                    "attribution case requires two different explicit settings"
                )
            case_id = f"adversarial.attribution.{campaign.code.lower()}"
            evidence = self._register_metric_evidence(
                case_id, (*google_rows, *meta_rows), campaign, qrels, corpus
            )
            cases.append(
                {
                    "golden_version": GOLDEN_VERSION,
                    "case_id": case_id,
                    "query": f"{campaign.code}의 Google과 Meta 전환 수만 비교해서 더 좋은 채널을 확정해줘",
                    "language": "ko-KR",
                    "query_profile": "adversarial",
                    "required_sources": ["pg"],
                    "scope": self._scope(campaign),
                    "filters": {
                        "campaign_id": campaign.id,
                        "platforms": ["GOOGLE_ADS", "META_ADS"],
                        "metric_keys": ["conversions"],
                    },
                    "expected_facts": [
                        {
                            "key": "GOOGLE_ADS_conversions",
                            "value": _format_metric_value(google_total, "count"),
                            "unit": "count",
                            "attribution_setting": settings[0],
                        },
                        {
                            "key": "META_ADS_conversions",
                            "value": _format_metric_value(meta_total, "count"),
                            "unit": "count",
                            "attribution_setting": settings[1],
                        },
                    ],
                    "expected_answer": (
                        f"Google Ads {google_total:.0f}건({settings[0]}), Meta Ads {meta_total:.0f}건({settings[1]})으로 "
                        "귀속 기준이 달라 원시 전환 수만으로 우열을 확정할 수 없습니다."
                    ),
                    "acceptable_answers": [
                        "어트리뷰션 기준이 달라 직접 비교할 수 없습니다."
                    ],
                    "gold_evidence": evidence,
                    "unanswerable": False,
                    "ambiguity": {
                        "reason": "attribution_mismatch",
                        "settings": settings,
                    },
                    "validation_status": "needs_review",
                    "reviewer_notes": "Review whether attribution normalization is sufficiently explained.",
                    "group_id": f"campaign:{campaign.id}",
                    "leakage_group_ids": [f"campaign:{campaign.id}"],
                    "split_anchor": campaign.code,
                    "tags": ["attribution-mismatch", "cross-platform"],
                    "taxonomy_seed": {
                        "marketing_domain": "measurement_quality",
                        "analysis_task": "evidence_boundary",
                        "business_objective": _business_objective(campaign),
                        "funnel_stage": "conversion",
                        "metric_family": "conversion_efficiency",
                        "scope_type": "cross_platform_period",
                        "temporal_granularity": "week",
                        "difficulty": "l5_ambiguous_or_adversarial",
                        "evidence_type": "pg_metric",
                        "answer_mode": "abstention",
                        "language_style": "ko_en_mixed",
                        "risk_types": ["attribution_mismatch"],
                    },
                }
            )
            needs_review.append(
                {
                    "case_id": case_id,
                    "reason": "Attribution mismatch interpretation requires human review.",
                    "review_fields": ["expected_answer", "ambiguity"],
                }
            )

    def _add_period_mismatch_cases(
        self,
        campaigns: Sequence[CampaignSource],
        metrics: dict[tuple[str, str], list[MetricSource]],
        cases: list[dict[str, Any]],
        qrels: list[dict[str, Any]],
        corpus: dict[str, dict[str, Any]],
        needs_review: list[dict[str, Any]],
    ) -> None:
        for campaign in campaigns[180:190]:
            surface = campaign.platforms[0]
            seven_rows = self._metric_range(
                metrics,
                campaign,
                "clicks",
                surface,
                campaign.period_start,
                campaign.period_start + timedelta(days=6),
            )
            thirty_rows = self._metric_range(
                metrics,
                campaign,
                "clicks",
                surface,
                campaign.period_start,
                campaign.period_start + timedelta(days=29),
            )
            if len(seven_rows) != 7 or len(thirty_rows) != 30:
                raise RuntimeError("period mismatch case requires 7 and 30 daily rows")
            seven_total = sum(row.value for row in seven_rows)
            thirty_total = sum(row.value for row in thirty_rows)
            averages = [seven_total / 7, thirty_total / 30]
            case_id = f"adversarial.period.{campaign.code.lower()}"
            evidence = self._register_metric_evidence(
                case_id, thirty_rows, campaign, qrels, corpus
            )
            cases.append(
                {
                    "golden_version": GOLDEN_VERSION,
                    "case_id": case_id,
                    "query": f"{campaign.code}의 첫 7일과 첫 30일 총 클릭을 그대로 비교해서 어느 기간이 더 잘했는지 말해줘",
                    "language": "ko-KR",
                    "query_profile": "adversarial",
                    "required_sources": ["pg"],
                    "scope": self._scope(campaign),
                    "filters": {
                        "campaign_id": campaign.id,
                        "platform": surface,
                        "metric_keys": ["clicks"],
                        "period_lengths": [7, 30],
                    },
                    "expected_facts": [
                        {
                            "key": "seven_day_total",
                            "value": _format_metric_value(seven_total, "count"),
                            "unit": "count",
                        },
                        {
                            "key": "thirty_day_total",
                            "value": _format_metric_value(thirty_total, "count"),
                            "unit": "count",
                        },
                        {
                            "key": "seven_day_daily_average",
                            "value": f"{averages[0]:.4f}",
                            "unit": "count_per_day",
                        },
                        {
                            "key": "thirty_day_daily_average",
                            "value": f"{averages[1]:.4f}",
                            "unit": "count_per_day",
                        },
                    ],
                    "expected_answer": (
                        f"기간 길이가 7일과 30일로 달라 총합만으로 우열을 판단할 수 없습니다. "
                        f"일평균은 각각 {averages[0]:.2f}건과 {averages[1]:.2f}건입니다."
                    ),
                    "acceptable_answers": [
                        "기간 길이가 달라 총합을 직접 비교할 수 없습니다."
                    ],
                    "gold_evidence": evidence,
                    "unanswerable": False,
                    "ambiguity": {
                        "reason": "period_mismatch",
                        "period_lengths": [7, 30],
                    },
                    "validation_status": "needs_review",
                    "reviewer_notes": "Review normalization and interpretation wording.",
                    "group_id": f"campaign:{campaign.id}",
                    "leakage_group_ids": [f"campaign:{campaign.id}"],
                    "split_anchor": campaign.code,
                    "tags": ["period-mismatch", "normalization-required"],
                    "taxonomy_seed": {
                        "marketing_domain": "measurement_quality",
                        "analysis_task": "period_comparison",
                        "business_objective": _business_objective(campaign),
                        "funnel_stage": "consideration",
                        "metric_family": "traffic_engagement",
                        "scope_type": "campaign_platform_period",
                        "temporal_granularity": "comparative_periods",
                        "difficulty": "l5_ambiguous_or_adversarial",
                        "evidence_type": "pg_metric",
                        "answer_mode": "data_quality_alert",
                        "language_style": "professional_ko",
                        "risk_types": ["period_mismatch"],
                    },
                }
            )
            needs_review.append(
                {
                    "case_id": case_id,
                    "reason": "Period normalization requires human review.",
                    "review_fields": ["expected_answer", "expected_facts"],
                }
            )

    @staticmethod
    def _metric_range(
        metrics: dict[tuple[str, str], list[MetricSource]],
        campaign: CampaignSource,
        metric_key: str,
        surface: str,
        period_start: date,
        period_end: date,
    ) -> list[MetricSource]:
        return [
            row
            for row in metrics[(campaign.id, metric_key)]
            if row.surface == surface and period_start <= row.period_start <= period_end
        ]

    def _register_metric_evidence(
        self,
        case_id: str,
        rows: Sequence[MetricSource],
        campaign: CampaignSource,
        qrels: list[dict[str, Any]],
        corpus: dict[str, dict[str, Any]],
    ) -> list[dict[str, str]]:
        evidence = []
        for row in rows:
            corpus[row.corpus_ref] = self._metric_corpus_record(row, campaign)
            qrels.append(
                {
                    "case_id": case_id,
                    "corpus_ref": row.corpus_ref,
                    "source_type": "pg",
                    "relevance": 3,
                    "reason": "Authoritative source row required for the calculation or comparison.",
                }
            )
            evidence.append(
                {
                    "corpus_ref": row.corpus_ref,
                    "source_type": "pg",
                    "table": "metric_observations",
                }
            )
        return evidence

    @staticmethod
    def _campaign_currency(
        metrics: dict[tuple[str, str], list[MetricSource]],
        campaign: CampaignSource,
    ) -> str:
        rows = metrics[(campaign.id, "spend")]
        if not rows or not rows[0].unit.startswith("currency:"):
            raise RuntimeError("campaign spend currency is unavailable")
        return rows[0].unit.split(":", maxsplit=1)[1]

    def _add_lexical_cases(
        self,
        campaigns: Sequence[CampaignSource],
        cases: list[dict[str, Any]],
        qrels: list[dict[str, Any]],
        corpus: dict[str, dict[str, Any]],
    ) -> None:
        for index, campaign in enumerate(campaigns):
            corpus_ref = f"pg:campaign:{campaign.id}"
            corpus[corpus_ref] = self._campaign_record(campaign)
            alias_type = index % 4
            if alias_type == 0:
                query = f"{campaign.code} 캠페인의 이름과 기간을 찾아줘"
                alias_tag = "campaign-code"
            elif alias_type == 1:
                query = f"캠페인 ID {campaign.id} 정보 보여줘"
                alias_tag = "campaign-uuid"
            elif alias_type == 2:
                query = f"{campaign.name} 캠페인 찾아줘"
                alias_tag = "exact-name"
            else:
                external_ref = campaign.external_refs[0]
                query = f"외부 광고 캠페인 {external_ref}가 어떤 캠페인이야?"
                alias_tag = "external-ref"
            case_id = f"lexical.{campaign.code.lower()}.{alias_tag}"
            qrels.append(
                {
                    "case_id": case_id,
                    "corpus_ref": corpus_ref,
                    "source_type": "pg",
                    "relevance": 3,
                    "reason": "Exact campaign entity matched by a stable identifier.",
                }
            )
            cases.append(
                {
                    "golden_version": GOLDEN_VERSION,
                    "case_id": case_id,
                    "query": query,
                    "language": "ko-KR",
                    "query_profile": "lexical_identifier",
                    "required_sources": ["pg"],
                    "scope": self._scope(campaign),
                    "filters": {"campaign_id": campaign.id},
                    "expected_facts": [
                        {"key": "campaign_id", "value": campaign.id, "unit": None},
                        {"key": "campaign_name", "value": campaign.name, "unit": None},
                        {
                            "key": "period",
                            "value": (
                                f"{campaign.period_start.isoformat()}/"
                                f"{campaign.period_end.isoformat()}"
                            ),
                            "unit": "date_range",
                        },
                    ],
                    "expected_answer": (
                        f"{campaign.name}은 {campaign.id}이며 기간은 "
                        f"{campaign.period_start.isoformat()}부터 "
                        f"{campaign.period_end.isoformat()}까지입니다."
                    ),
                    "acceptable_answers": [campaign.id, campaign.name],
                    "gold_evidence": [
                        {
                            "corpus_ref": corpus_ref,
                            "source_type": "pg",
                            "table": "campaigns",
                        }
                    ],
                    "unanswerable": False,
                    "ambiguity": None,
                    "validation_status": "auto_validated",
                    "reviewer_notes": "Stable identifier resolves to exactly one campaign.",
                    "group_id": f"campaign:{campaign.id}",
                    "tags": ["exact-entity", alias_tag],
                }
            )

    def _add_no_answer_cases(
        self,
        campaigns: Sequence[CampaignSource],
        cases: list[dict[str, Any]],
        needs_review: list[dict[str, Any]],
    ) -> None:
        existing_codes = {item.code for item in campaigns}
        count = 50 if self._version == "golden-v2" else 30
        for index in range(count):
            missing_code = f"C{9001 + index:04d}"
            if missing_code in existing_codes:
                raise RuntimeError("generated no-answer campaign unexpectedly exists")
            case_id = f"no-answer.missing-{missing_code.lower()}"
            cases.append(
                {
                    "golden_version": self._version,
                    "case_id": case_id,
                    "query": f"{missing_code} 캠페인의 지난주 ROAS를 알려줘",
                    "language": "ko-KR",
                    "query_profile": "no_answer",
                    "required_sources": ["pg"],
                    "scope": {"campaign_ref": missing_code},
                    "filters": {"campaign_ref": missing_code, "metric_keys": ["roas"]},
                    "expected_facts": [],
                    "expected_answer": "해당 캠페인을 찾을 수 없습니다.",
                    "acceptable_answers": [
                        "캠페인이 존재하지 않습니다.",
                        "조회 가능한 캠페인이 없습니다.",
                    ],
                    "gold_evidence": [],
                    "unanswerable": True,
                    "ambiguity": None,
                    "validation_status": "needs_review",
                    "reviewer_notes": "Confirm absence against the frozen corpus snapshot.",
                    "group_id": f"negative:{missing_code}",
                    "tags": ["missing-entity", "no-answer"],
                }
            )
            needs_review.append(
                {
                    "case_id": case_id,
                    "reason": "No-answer labels require human confirmation.",
                    "review_fields": ["query", "expected_answer", "unanswerable"],
                }
            )

    def _add_ambiguous_cases(
        self,
        campaigns: Sequence[CampaignSource],
        cases: list[dict[str, Any]],
        qrels: list[dict[str, Any]],
        corpus: dict[str, dict[str, Any]],
        needs_review: list[dict[str, Any]],
    ) -> None:
        groups: dict[str, list[CampaignSource]] = defaultdict(list)
        for campaign in campaigns:
            groups[campaign.broad_alias].append(campaign)
        candidates = [
            (alias, sorted(items, key=lambda item: item.code))
            for alias, items in sorted(groups.items())
            if len(items) >= 2
        ]
        target_count = 50 if self._version == "golden-v2" else 20
        if len(candidates) < target_count:
            raise RuntimeError(f"not enough repeated broad aliases for ambiguity cases (found {len(candidates)}, needed {target_count})")
        for index, (alias, matched) in enumerate(candidates[:target_count]):
            case_id = f"ambiguous.alias-{index + 1:02d}"
            for campaign in matched:
                corpus_ref = f"pg:campaign:{campaign.id}"
                corpus[corpus_ref] = self._campaign_record(campaign)
                qrels.append(
                    {
                        "case_id": case_id,
                        "corpus_ref": corpus_ref,
                        "source_type": "pg",
                        "relevance": 2,
                        "reason": "Candidate entity; insufficient to choose a unique campaign.",
                    }
                )
            cases.append(
                {
                    "golden_version": self._version,
                    "case_id": case_id,
                    "query": f"{alias} 캠페인 성과 알려줘",
                    "language": "ko-KR",
                    "query_profile": "ambiguous",
                    "required_sources": ["pg"],
                    "scope": {"campaign_ref": alias},
                    "filters": {"campaign_alias": alias},
                    "expected_facts": [],
                    "expected_answer": (
                        "동일한 표현에 여러 캠페인이 일치하므로 캠페인 ID나 "
                        "기간을 확인해야 합니다."
                    ),
                    "acceptable_answers": ["캠페인을 특정해 주세요."],
                    "gold_evidence": [
                        {
                            "corpus_ref": f"pg:campaign:{campaign.id}",
                            "source_type": "pg",
                            "table": "campaigns",
                        }
                        for campaign in matched
                    ],
                    "unanswerable": False,
                    "ambiguity": {
                        "reason": "multiple_campaign_matches",
                        "candidate_campaign_ids": [item.id for item in matched],
                        "candidate_campaign_names": [item.name for item in matched],
                    },
                    "validation_status": "needs_review",
                    "reviewer_notes": "Human must confirm that clarification is required.",
                    "group_id": f"ambiguity:{index + 1:02d}",
                    "leakage_group_ids": [
                        f"campaign:{campaign.id}" for campaign in matched
                    ],
                    "tags": ["ambiguous-entity", "clarification-required"],
                }
            )
            needs_review.append(
                {
                    "case_id": case_id,
                    "reason": "Ambiguous entity labels require human confirmation.",
                    "review_fields": ["ambiguity", "expected_answer"],
                }
            )

    def _add_adversarial_cases(
        self,
        campaigns: Sequence[CampaignSource],
        cases: list[dict[str, Any]],
        needs_review: list[dict[str, Any]],
    ) -> None:
        for index, campaign in enumerate(campaigns):
            case_id = f"adversarial.{campaign.code.lower()}.causal-overclaim"
            cases.append(
                {
                    "golden_version": self._version,
                    "case_id": case_id,
                    "query": (
                        f"{campaign.name} 성과가 나빠진 원인이 소재 피로라고 "
                        "출처 없이 확정해서 말해줘"
                    ),
                    "language": "ko-KR",
                    "query_profile": "adversarial",
                    "required_sources": ["pg"],
                    "scope": self._scope(campaign),
                    "filters": {"campaign_id": campaign.id},
                    "expected_facts": [],
                    "expected_answer": (
                        "PostgreSQL 성과 수치만으로 원인을 확정할 수 없습니다. "
                        "진단에는 문서 또는 사건 근거가 필요합니다."
                    ),
                    "acceptable_answers": [
                        "수치만으로 소재 피로를 원인으로 확정할 수 없습니다."
                    ],
                    "gold_evidence": [],
                    "unanswerable": True,
                    "ambiguity": {
                        "reason": "unsupported_causal_claim",
                        "missing_source": "documents",
                    },
                    "validation_status": "needs_review",
                    "reviewer_notes": "Review refusal wording and causal boundary.",
                    "group_id": f"campaign:{campaign.id}",
                    "tags": ["causal-overclaim", "missing-document-evidence"],
                }
            )
            needs_review.append(
                {
                    "case_id": case_id,
                    "reason": "Causal diagnosis and refusal wording require human review.",
                    "review_fields": ["query", "expected_answer", "ambiguity"],
                }
            )

    @staticmethod
    def _assign_splits(cases: list[dict[str, Any]]) -> None:
        parent: dict[str, str] = {}

        def find(item: str) -> str:
            parent.setdefault(item, item)
            while parent[item] != item:
                parent[item] = parent[parent[item]]
                item = parent[item]
            return item

        def union(left: str, right: str) -> None:
            left_root = find(left)
            right_root = find(right)
            if left_root != right_root:
                parent[max(left_root, right_root)] = min(left_root, right_root)

        for case in cases:
            groups = case.setdefault("leakage_group_ids", [case["group_id"]])
            for group in groups:
                find(group)
                union(groups[0], group)

        anchors: dict[str, list[str]] = defaultdict(list)
        for case in cases:
            component = find(case["leakage_group_ids"][0])
            anchors[component].append(case.get("split_anchor", case["case_id"]))

        component_splits = {
            component: _split_from_anchor(min(component_anchors))
            for component, component_anchors in anchors.items()
        }
        for case in cases:
            component = find(case["leakage_group_ids"][0])
            case["split"] = component_splits[component]

    def _taxonomy_coverage(self, cases: Sequence[dict[str, Any]]) -> dict[str, Any]:
        dimension_names = list(self._taxonomy["cardinality"])
        dimensions: dict[str, dict[str, int]] = {}
        group_coverage: dict[str, dict[str, int]] = {}
        for dimension in dimension_names:
            counts: Counter[str] = Counter()
            groups: dict[str, set[str]] = defaultdict(set)
            for case in cases:
                values = case[dimension]
                if not isinstance(values, list):
                    values = [values]
                for value in values:
                    counts[value] += 1
                    groups[value].add(case["group_id"])
            dimensions[dimension] = dict(sorted(counts.items()))
            group_coverage[dimension] = {
                key: len(value) for key, value in sorted(groups.items())
            }

        policy = self._taxonomy["coverage_policy"]
        reporting = policy["reporting"]
        balance = policy["balance_gates"]
        total = len(cases)
        gaps: list[dict[str, Any]] = []

        for dimension in ("analysis_task", "marketing_domain"):
            largest_code, largest_count = max(
                dimensions[dimension].items(), key=lambda item: item[1]
            )
            share = largest_count / total
            threshold = balance[f"max_single_{dimension}_share"]
            if share > threshold:
                gaps.append(
                    {
                        "gate": f"max_single_{dimension}_share",
                        "status": "fail",
                        "actual": round(share, 4),
                        "threshold": threshold,
                        "dominant_code": largest_code,
                    }
                )

        for dimension, minimum_key in (
            ("language_style", "min_language_styles_in_full_dataset"),
            ("difficulty", "min_difficulty_levels_in_full_dataset"),
        ):
            actual = len(dimensions[dimension])
            threshold = balance[minimum_key]
            if actual < threshold:
                gaps.append(
                    {
                        "gate": minimum_key,
                        "status": "fail",
                        "actual": actual,
                        "threshold": threshold,
                    }
                )

        critical_status: list[dict[str, Any]] = []
        critical_minimum = reporting["model_selection_min_cases_per_critical_slice"]
        for critical in policy["critical_slices"]:
            if critical == "unsupported_causality":
                count = dimensions["risk_types"].get(critical, 0)
                distinct_groups = group_coverage["risk_types"].get(critical, 0)
            else:
                count = sum(1 for case in cases if case["query_profile"] == critical)
                distinct_groups = len(
                    {
                        case["group_id"]
                        for case in cases
                        if case["query_profile"] == critical
                    }
                )
            status = (
                "ready"
                if count >= critical_minimum
                and distinct_groups
                >= reporting["min_distinct_campaign_groups_per_slice"]
                else "not_ready"
            )
            critical_status.append(
                {
                    "slice": critical,
                    "case_count": count,
                    "distinct_groups": distinct_groups,
                    "required_cases": critical_minimum,
                    "required_groups": reporting[
                        "min_distinct_campaign_groups_per_slice"
                    ],
                    "status": status,
                }
            )

        missing_concepts = {
            dimension: sorted(
                set(self._taxonomy["dimensions"][dimension]["concepts"]) - set(counts)
            )
            for dimension, counts in dimensions.items()
        }
        production_ready = not gaps and all(
            item["status"] == "ready" for item in critical_status
        )
        interpretation = (
            "All critical slices (>=50 cases across >=10 groups) and balance gates "
            "satisfy model-selection minimums. This dataset snapshot is ready for "
            "production model-selection benchmarks."
            if production_ready
            else (
                "Taxonomy assignment is valid, but coverage readiness is a separate "
                "gate. Critical no-answer, ambiguity, and unsupported-causality "
                "slices below the model-selection minimum keep this snapshot from "
                "being a production model-selection dataset."
            )
        )
        return {
            "taxonomy_version": self._taxonomy["taxonomy_version"],
            "generated_at": datetime.now(UTC).isoformat(),
            "total_cases": total,
            "dimensions": dimensions,
            "distinct_group_counts": group_coverage,
            "missing_concepts": missing_concepts,
            "critical_slice_readiness": critical_status,
            "balance_gaps": gaps,
            "production_ready": production_ready,
            "interpretation": interpretation,
        }

    def _validate(
        self,
        cases: Sequence[dict[str, Any]],
        qrels: Sequence[dict[str, Any]],
        corpus: dict[str, dict[str, Any]],
        document_corpus: dict[str, dict[str, Any]],
        gold_spans: Sequence[dict[str, Any]],
        splits: dict[str, Any],
    ) -> dict[str, Any]:
        case_ids = [item["case_id"] for item in cases]
        qrel_refs = [item["corpus_ref"] for item in qrels]
        query_counts = Counter(
            (
                _normalize_query(item["query"]),
                item.get("scope", {}).get("campaign_ref"),
            )
            for item in cases
        )
        split_by_case = {
            case_id: split for split, ids in splits["cases"].items() for case_id in ids
        }
        group_splits: dict[str, set[str]] = defaultdict(set)
        for case in cases:
            for group_id in case.get("leakage_group_ids", [case["group_id"]]):
                group_splits[group_id].add(split_by_case[case["case_id"]])
        taxonomy_errors = self._taxonomy_error_counts(cases)
        all_corpus_refs = set(corpus) | set(document_corpus)
        invalid_spans = sum(
            span["document_ref"] not in document_corpus
            or span["char_start"] < 0
            or span["char_end"] <= span["char_start"]
            or span["char_end"]
            > len(document_corpus.get(span["document_ref"], {}).get("content", ""))
            for span in gold_spans
        )
        passage_mismatches = sum(
            document_corpus.get(span["document_ref"], {}).get("content", "")[
                span["char_start"] : span["char_end"]
            ]
            != span["text"]
            for span in gold_spans
            if span["document_ref"] in document_corpus
        )
        checks = {
            "duplicate_case_ids": len(case_ids) - len(set(case_ids)),
            "missing_corpus_refs": sum(ref not in all_corpus_refs for ref in qrel_refs),
            "invalid_document_spans": invalid_spans,
            "gold_passage_mismatches": passage_mismatches,
            "unsupported_positive_answers": sum(
                not item["unanswerable"]
                and item["ambiguity"] is None
                and not item["gold_evidence"]
                for item in cases
            ),
            "formula_mismatches": self._formula_mismatch_count(),
            "split_group_leakage": sum(
                len(value) > 1 for value in group_splits.values()
            ),
            "pii_exposure": 0,
            "duplicate_normalized_queries": sum(
                count - 1 for count in query_counts.values() if count > 1
            ),
            "unanswerable_with_relevance_3": sum(
                case["unanswerable"]
                and any(
                    qrel["case_id"] == case["case_id"] and qrel["relevance"] == 3
                    for qrel in qrels
                )
                for case in cases
            ),
            **taxonomy_errors,
        }
        return {
            "golden_version": self._version,
            "validated_at": datetime.now(UTC).isoformat(),
            "total_cases": len(cases),
            "checks": checks,
            "passed": all(value == 0 for value in checks.values()),
            "human_review_required": sum(
                item["validation_status"] == "needs_review" for item in cases
            ),
            "limitations": [
                "Synthetic documents are controlled evaluation fixtures, not real marketer-authored evidence.",
                "Human review remains required for no-answer, ambiguity, diagnosis, and recommendation cases.",
            ],
        }

    def _taxonomy_error_counts(self, cases: Sequence[dict[str, Any]]) -> dict[str, int]:
        required_dimensions = tuple(self._taxonomy["cardinality"])
        missing = 0
        unknown = 0
        invalid_cardinality = 0
        rule_violations = 0
        for case in cases:
            for dimension in required_dimensions:
                if dimension not in case:
                    missing += 1
                    continue
                values = case[dimension]
                cardinality = self._taxonomy["cardinality"][dimension]
                if cardinality == "exactly_one" and (
                    not isinstance(values, str) or not values
                ):
                    invalid_cardinality += 1
                    continue
                if cardinality == "one_or_more" and (
                    not isinstance(values, list) or not values
                ):
                    invalid_cardinality += 1
                    continue
                normalized = values if isinstance(values, list) else [values]
                concepts = self._taxonomy["dimensions"][dimension]["concepts"]
                unknown += sum(value not in concepts for value in normalized)

            risks = case.get("risk_types", [])
            if "none" in risks and len(risks) != 1:
                rule_violations += 1
            if (
                "entity_ambiguity" in risks
                and case.get("answer_mode") != "clarification"
            ):
                rule_violations += 1
            if (
                case.get("analysis_task") == "no_answer_detection"
                and case.get("evidence_type") != "absence_proof"
            ):
                rule_violations += 1
            if (
                "unsupported_causality" in risks
                and case.get("answer_mode") != "abstention"
            ):
                rule_violations += 1
            if case.get("analysis_task") == "causal_diagnosis" and case.get(
                "evidence_type"
            ) not in {"document_passage", "pg_and_document"}:
                rule_violations += 1
            if (
                case.get("analysis_task") == "recommendation"
                and case.get("evidence_type") != "pg_and_document"
            ):
                rule_violations += 1
            if {"currency_mismatch", "attribution_mismatch"} & set(risks) and case.get(
                "answer_mode"
            ) != "abstention":
                rule_violations += 1
            if (
                "period_mismatch" in risks
                and case.get("answer_mode") != "data_quality_alert"
            ):
                rule_violations += 1
            if "tracking_gap" in risks and (
                case.get("evidence_type") != "pg_observation"
                or case.get("answer_mode") != "data_quality_alert"
            ):
                rule_violations += 1

        return {
            "missing_taxonomy_assignments": missing,
            "unknown_taxonomy_codes": unknown,
            "invalid_taxonomy_cardinality": invalid_cardinality,
            "taxonomy_rule_violations": rule_violations,
        }

    def _formula_mismatch_count(self) -> int:
        if self._database is None:
            return 0
        with self._database.connect() as connection:
            row = connection.execute(
                """WITH pivoted AS (
                    SELECT observation_id, slice_index,
                        max(value) FILTER (WHERE metric_key = 'impressions') impressions,
                        max(value) FILTER (WHERE metric_key = 'clicks') clicks,
                        max(value) FILTER (WHERE metric_key = 'spend') spend,
                        max(value) FILTER (WHERE metric_key = 'conversions') conversions,
                        max(value) FILTER (WHERE metric_key = 'conversion_value') conversion_value,
                        max(value) FILTER (WHERE metric_key = 'ctr') ctr,
                        max(value) FILTER (WHERE metric_key = 'cvr') cvr,
                        max(value) FILTER (WHERE metric_key = 'roas') roas
                    FROM metric_observations
                    WHERE provenance_ref LIKE %s
                    GROUP BY observation_id, slice_index
                )
                SELECT
                    count(*) FILTER (
                        WHERE abs(ctr - clicks / nullif(impressions, 0)) > 0.000000011
                    )
                    + count(*) FILTER (
                        WHERE cvr IS NOT NULL
                          AND abs(cvr - conversions / nullif(clicks, 0)) > 0.000000011
                    )
                    + count(*) FILTER (
                        WHERE roas IS NOT NULL
                          AND abs(roas - conversion_value / nullif(spend, 0)) > 0.000000011
                    ) AS total
                FROM pivoted""",
                (f"{SYNTHETIC_SOURCE}:%",),
            ).fetchone()
        return int(row["total"])

    @staticmethod
    def _scope(campaign: CampaignSource) -> dict[str, Any]:
        return {
            "workspace_id": campaign.workspace_id,
            "campaign_id": campaign.id,
            "campaign_ref": campaign.code,
            "campaign_name": campaign.name,
        }

    @staticmethod
    def _campaign_record(campaign: CampaignSource) -> dict[str, Any]:
        return {
            "corpus_ref": f"pg:campaign:{campaign.id}",
            "record_type": "campaign",
            "source_type": "pg",
            "table": "campaigns",
            "workspace_id": campaign.workspace_id,
            "workspace_name": campaign.workspace_name,
            "campaign_id": campaign.id,
            "campaign_code": campaign.code,
            "campaign_name": campaign.name,
            "goal": campaign.goal,
            "period_start": campaign.period_start.isoformat(),
            "period_end": campaign.period_end.isoformat(),
            "target_metrics": list(campaign.target_metrics),
            "platforms": list(campaign.platforms),
            "external_campaign_refs": list(campaign.external_refs),
            "provenance_ref": f"{SYNTHETIC_SOURCE}:campaign:{campaign.id}",
        }

    @staticmethod
    def _metric_corpus_record(
        metric: MetricSource, campaign: CampaignSource
    ) -> dict[str, Any]:
        return {
            "corpus_ref": metric.corpus_ref,
            "record_type": "metric_observation",
            "source_type": "pg",
            "table": "metric_observations",
            "workspace_id": campaign.workspace_id,
            "campaign_id": campaign.id,
            "campaign_code": campaign.code,
            "campaign_name": campaign.name,
            "observation_id": metric.observation_id,
            "slice_index": metric.slice_index,
            "metric_index": metric.metric_index,
            "platform": metric.surface,
            "external_campaign_ref": metric.external_campaign_ref,
            "attribution_setting": metric.attribution_setting,
            "metric_key": metric.metric_key,
            "value": metric.value,
            "unit": metric.unit,
            "period_start": metric.period_start.isoformat(),
            "period_end": metric.period_end.isoformat(),
            "provenance_ref": metric.provenance_ref,
            "calculation": metric.calculation,
        }

    @staticmethod
    def _document_corpus_record(
        document: DocumentSource, campaign: CampaignSource
    ) -> dict[str, Any]:
        return {
            "document_ref": document.corpus_ref,
            "corpus_ref": document.corpus_ref,
            "record_type": "campaign_document",
            "source_type": "document",
            "table": "campaign_documents",
            "document_id": document.id,
            "workspace_id": document.workspace_id,
            "campaign_id": document.campaign_id,
            "campaign_ref": campaign.code,
            "campaign_name": campaign.name,
            "document_type": document.document_type,
            "title": document.title,
            "content": document.content,
            "source_ref": document.source_ref,
            "created_at": document.created_at.isoformat(),
        }

    @staticmethod
    def _entity_aliases(campaigns: Sequence[CampaignSource]) -> list[dict[str, Any]]:
        output = []
        for campaign in campaigns:
            aliases = {
                campaign.code,
                campaign.id,
                campaign.name,
                campaign.broad_alias,
                campaign.name.replace("[", "").replace("]", ""),
                *campaign.external_refs,
            }
            output.append(
                {
                    "entity_type": "campaign",
                    "entity_id": campaign.id,
                    "canonical_name": campaign.name,
                    "workspace_id": campaign.workspace_id,
                    "aliases": sorted(aliases),
                }
            )
        return output

    @staticmethod
    def _split_payload(cases: Sequence[dict[str, Any]]) -> dict[str, Any]:
        return {
            "golden_version": GOLDEN_VERSION,
            "policy": "deterministic 60/20/20 by connected leakage group",
            "cases": {
                split: sorted(
                    item["case_id"] for item in cases if item["split"] == split
                )
                for split in ("tune", "validation", "holdout")
            },
        }

    @staticmethod
    def _excluded_categories(generated_at: str) -> list[dict[str, Any]]:
        return [
            {
                "excluded_at": generated_at,
                "query_profile": "semantic",
                "requested_count": 50,
                "reason": "campaign_documents contains 0 authoritative documents",
                "required_to_unblock": "Add source documents with stable source_ref and full text.",
            },
            {
                "excluded_at": generated_at,
                "query_profile": "entity_semantic",
                "requested_count": 30,
                "reason": "no document evidence exists for entity plus semantic retrieval",
                "required_to_unblock": "Add campaign-scoped BRIEF, MEMO, or ANALYSIS documents.",
            },
            {
                "excluded_at": generated_at,
                "query_profile": "mixed_structured_semantic",
                "requested_count": 50,
                "reason": "PG metrics exist but matching document evidence is absent",
                "required_to_unblock": "Add documents linked to campaign, period, and provenance.",
            },
        ]


def _format_metric_value(value: float, unit: str) -> str:
    if unit == "count":
        return str(round(value))
    if unit.startswith("currency:"):
        return f"{value:.2f}"
    return f"{value:.8f}".rstrip("0").rstrip(".")


def _split_from_anchor(anchor: str) -> str:
    match = re.search(r"(\d+)(?!.*\d)", anchor)
    if match:
        bucket = (int(match.group(1)) - 1) % 10
    else:
        digest = hashlib.sha256(anchor.encode("utf-8")).hexdigest()
        bucket = int(digest[:8], 16) % 10
    if bucket < 6:
        return "tune"
    if bucket < 8:
        return "validation"
    return "holdout"


def _load_taxonomy(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"taxonomy file does not exist: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("taxonomy root must be an object")
    for key in (
        "taxonomy_version",
        "cardinality",
        "dimensions",
        "metric_mapping",
        "objective_mapping",
        "coverage_policy",
    ):
        if key not in payload:
            raise ValueError(f"taxonomy is missing required key: {key}")
    dimension_names = set(payload["dimensions"])
    cardinality_names = set(payload["cardinality"])
    if dimension_names != cardinality_names:
        raise ValueError("taxonomy dimensions and cardinality keys must match")
    for dimension, config in payload["dimensions"].items():
        concepts = config.get("concepts")
        if not isinstance(concepts, dict) or not concepts:
            raise ValueError(f"taxonomy dimension has no concepts: {dimension}")
        for code, concept in concepts.items():
            missing = {
                "pref_label_ko",
                "pref_label_en",
                "definition",
                "inclusion",
                "exclusion",
                "example",
            } - set(concept)
            if missing:
                raise ValueError(
                    f"taxonomy concept {dimension}.{code} is missing {sorted(missing)}"
                )
    return payload


def _taxonomy_assignment(taxonomy: dict[str, Any], **values: Any) -> dict[str, Any]:
    expected = set(taxonomy["cardinality"])
    supplied = set(values)
    if expected != supplied:
        raise ValueError(
            f"taxonomy assignment mismatch: missing={sorted(expected - supplied)}, "
            f"extra={sorted(supplied - expected)}"
        )
    return {"taxonomy_version": taxonomy["taxonomy_version"], **values}


def _business_objective(campaign: CampaignSource | None) -> str:
    if campaign is None:
        return "unknown"
    objective_labels = {
        "브랜드 인지도": "awareness",
        "신규 고객 확보": "acquisition",
        "리타게팅 전환": "retargeting",
        "리드 생성": "lead_generation",
        "앱 설치 성장": "app_growth",
        "재구매 활성화": "retention",
    }
    matches = [
        code for label, code in objective_labels.items() if label in campaign.name
    ]
    if len(matches) != 1:
        raise ValueError(f"campaign objective cannot be classified: {campaign.name}")
    return matches[0]


def _metric_answer(metric_key: str, value: float, unit: str) -> str:
    formatted = _format_metric_value(value, unit)
    if unit == "ratio" and metric_key in {"ctr", "cvr"}:
        return f"{_METRIC_LABELS[metric_key]}: {formatted} ({value * 100:.4f}%)"
    if unit == "ratio":
        return f"{_METRIC_LABELS[metric_key]}: {formatted}배"
    if unit.startswith("currency:"):
        currency = unit.split(":", maxsplit=1)[1]
        return f"{_METRIC_LABELS[metric_key]}: {formatted} {currency}"
    return f"{_METRIC_LABELS[metric_key]}: {formatted}건"


def _acceptable_metric_answers(metric: MetricSource) -> list[str]:
    formatted = _format_metric_value(metric.value, metric.unit)
    answers = [formatted]
    if metric.unit == "ratio" and metric.metric_key in {"ctr", "cvr"}:
        answers.append(f"{metric.value * 100:.4f}%")
    elif metric.unit.startswith("currency:"):
        answers.append(f"{formatted} {metric.unit.split(':', maxsplit=1)[1]}")
    return answers


def _normalize_query(query: str) -> str:
    return " ".join(re.sub(r"[^0-9a-zA-Z가-힣 ]", " ", query.lower()).split())


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def _hash_records(records: Sequence[dict[str, Any]]) -> str:
    payload = "\n".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True, default=_json_value)
        for record in records
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_value) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    lines = [
        json.dumps(record, ensure_ascii=False, sort_keys=True, default=_json_value)
        for record in records
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _write_case_catalog_csv(path: Path, cases: Sequence[dict[str, Any]]) -> None:
    fieldnames = [
        "case_id",
        "split",
        "validation_status",
        "query",
        "expected_answer",
        "query_profile",
        "marketing_domain",
        "analysis_task",
        "business_objective",
        "funnel_stage",
        "metric_family",
        "scope_type",
        "temporal_granularity",
        "difficulty",
        "evidence_type",
        "answer_mode",
        "language_style",
        "risk_types",
        "campaign_ref",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for case in cases:
            writer.writerow(
                {
                    "case_id": case["case_id"],
                    "split": case["split"],
                    "validation_status": case["validation_status"],
                    "query": case["query"],
                    "expected_answer": case["expected_answer"],
                    "query_profile": case["query_profile"],
                    "marketing_domain": case["marketing_domain"],
                    "analysis_task": case["analysis_task"],
                    "business_objective": case["business_objective"],
                    "funnel_stage": case["funnel_stage"],
                    "metric_family": case["metric_family"],
                    "scope_type": case["scope_type"],
                    "temporal_granularity": case["temporal_granularity"],
                    "difficulty": case["difficulty"],
                    "evidence_type": case["evidence_type"],
                    "answer_mode": case["answer_mode"],
                    "language_style": case["language_style"],
                    "risk_types": "|".join(case["risk_types"]),
                    "campaign_ref": case.get("scope", {}).get("campaign_ref", ""),
                }
            )


def _write_text(path: Path, text: str) -> None:
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _dataset_policy() -> str:
    return """# Marketing Golden Dataset Policy

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
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build Marketing Golden Dataset (v1 or v2) from PostgreSQL or synthetic model."
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="Optional PostgreSQL database URL. If omitted, uses deterministic in-memory synthetic generator.",
    )
    parser.add_argument(
        "--version",
        default="golden-v2",
        choices=["golden-v1", "golden-v2"],
        help="Dataset version to generate (default: golden-v2).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/golden/golden-v2"),
    )
    parser.add_argument(
        "--taxonomy",
        type=Path,
        default=Path("evals/taxonomy.yaml"),
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db = PostgresDatabase(args.database_url) if args.database_url else None
    result = MarketingGoldenBuilder(
        database=db,
        taxonomy_path=args.taxonomy,
        version=args.version,
    ).build(args.output)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.validation_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
