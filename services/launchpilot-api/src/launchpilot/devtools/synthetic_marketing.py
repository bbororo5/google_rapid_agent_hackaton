from __future__ import annotations

import argparse
import json
import os
import random
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from math import exp
from uuid import UUID, uuid5

from psycopg import Connection
from psycopg.types.json import Jsonb

from launchpilot.persistence.postgres import PostgresDatabase

DATASET_NAME = "synthetic-marketing-v1"
DATASET_NAMESPACE = UUID("d26bf75a-c58b-4d7d-841b-4e898cdd9e57")


@dataclass(frozen=True, slots=True)
class SyntheticConfig:
    workspaces: int = 3
    campaigns_per_workspace: int = 100
    days: int = 90
    start_date: date = date(2025, 1, 1)
    seed: int = 20260813

    def __post_init__(self) -> None:
        for name, value in (
            ("workspaces", self.workspaces),
            ("campaigns_per_workspace", self.campaigns_per_workspace),
            ("days", self.days),
        ):
            if value < 1:
                raise ValueError(f"{name} must be at least 1")

    @property
    def campaign_count(self) -> int:
        return self.workspaces * self.campaigns_per_workspace

    @property
    def observation_count(self) -> int:
        return self.campaign_count * self.days


@dataclass(frozen=True, slots=True)
class WorkspacePlan:
    id: UUID
    index: int
    name: str
    currency_code: str
    timezone: str


@dataclass(frozen=True, slots=True)
class CampaignPlan:
    id: UUID
    workspace: WorkspacePlan
    global_index: int
    name: str
    goal: str
    start: date
    end: date
    target_metrics: tuple[str, ...]
    platforms: tuple[str, ...]
    pattern: str
    daily_budget: float
    conversion_value: float
    quality: float


@dataclass(frozen=True, slots=True)
class MetricDatum:
    key: str
    value: float
    unit: str
    calculation: str | None = None


@dataclass(frozen=True, slots=True)
class PlatformDay:
    surface: str
    account_ref: str
    external_campaign_ref: str
    connector: str
    attribution_setting: str
    metrics: tuple[MetricDatum, ...]
    missing_reason: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentPlan:
    id: UUID
    campaign_id: UUID
    workspace_id: UUID
    document_type: str
    title: str
    content: str
    source_ref: str
    created_at: datetime


@dataclass(slots=True)
class SeedSummary:
    dataset: str = DATASET_NAME
    workspaces: int = 0
    campaigns: int = 0
    observations: int = 0
    platform_slices: int = 0
    metrics: int = 0
    partial_observations: int = 0
    documents: int = 0


_BRANDS = (
    "오로라",
    "런치파일럿",
    "모먼트",
    "그로우랩",
    "리프",
    "데일리픽",
    "브리즈",
    "스튜디오온",
    "플로우",
    "넥스트웨어",
)
_PRODUCTS = (
    "신제품",
    "프리미엄 플랜",
    "모바일 앱",
    "여름 컬렉션",
    "구독 서비스",
    "체험 패키지",
    "온라인 클래스",
    "웰컴 키트",
)
_AUDIENCES = (
    "신규 고객",
    "휴면 고객",
    "장바구니 이탈자",
    "20대 직장인",
    "소상공인",
    "기존 구매자",
    "고관여 방문자",
    "브랜드 검색자",
)
_OBJECTIVES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "신규 고객 확보",
        "신규 고객의 첫 구매를 확대하고 획득 비용을 안정화",
        ("conversions", "cpa", "roas"),
    ),
    (
        "리타게팅 전환",
        "고관여 방문자의 구매 전환과 광고 수익률을 개선",
        ("conversions", "cvr", "roas"),
    ),
    (
        "브랜드 인지도",
        "목표 고객 도달과 브랜드 메시지 노출을 확대",
        ("impressions", "clicks", "ctr"),
    ),
    (
        "앱 설치 성장",
        "모바일 앱 설치와 설치 후 핵심 행동을 확대",
        ("conversions", "cpa", "conversion_value"),
    ),
    (
        "리드 생성",
        "유효 상담 신청을 확보하고 리드당 비용을 절감",
        ("conversions", "cpa", "cvr"),
    ),
    (
        "재구매 활성화",
        "기존 고객의 반복 구매와 고객 가치를 확대",
        ("conversions", "conversion_value", "roas"),
    ),
)
_PATTERNS = (
    "steady",
    "growth",
    "fatigue",
    "launch_spike",
    "budget_cut",
    "tracking_gap",
    "midflight_recovery",
)
_PLATFORM_BASELINES = {
    "GOOGLE_ADS": {"ctr": 0.047, "cvr": 0.051, "cpm": 13_000.0},
    "META_ADS": {"ctr": 0.013, "cvr": 0.031, "cpm": 9_000.0},
    "YOUTUBE": {"ctr": 0.009, "cvr": 0.018, "cpm": 7_000.0},
}

_PATTERN_DOCUMENT_FACTS = {
    "steady": (
        "일별 변동은 정상 범위이며 노출과 클릭 흐름이 안정적으로 유지되었습니다.",
        "현재 입찰과 소재 구성을 유지하되 주간 변동 폭을 계속 관찰합니다.",
    ),
    "growth": (
        "예산 확대 이후 노출과 클릭이 함께 증가했고 전환 효율도 허용 범위를 유지했습니다.",
        "효율 하락 여부를 확인하면서 성과가 검증된 채널의 예산을 단계적으로 확대합니다.",
    ),
    "fatigue": (
        "반복 노출이 누적된 후 CTR과 CVR이 함께 하락해 소재 피로 신호가 관찰되었습니다.",
        "기존 소재의 노출 비중을 낮추고 메시지가 다른 신규 소재를 순차적으로 투입합니다.",
    ),
    "launch_spike": (
        "출시 직후 노출과 클릭이 급증한 뒤 초기 관심 효과가 완만하게 정상화되었습니다.",
        "초기 급증 구간을 상시 성과로 해석하지 말고 안정화 이후 값을 기준선으로 사용합니다.",
    ),
    "budget_cut": (
        "예산 축소 시점 이후 노출과 클릭이 동시에 감소했으며 효율 지표 변화는 제한적이었습니다.",
        "도달량 회복이 목표라면 효율이 유지되는 채널부터 예산을 복원합니다.",
    ),
    "tracking_gap": (
        "전환 태그 수집이 사흘간 누락되어 해당 기간의 전환 수와 ROAS를 완전한 값으로 볼 수 없습니다.",
        "태그 복구와 백필 여부를 확인하기 전에는 누락 기간의 전환 효율 판단을 보류합니다.",
    ),
    "midflight_recovery": (
        "중간 구간의 CTR과 CVR 하락 뒤 운영 조정 시점부터 두 지표가 점진적으로 회복되었습니다.",
        "회복이 확인된 조정안을 유지하고 다음 주에도 같은 지표 정의로 재검증합니다.",
    ),
}


def stable_uuid(*parts: object) -> UUID:
    return uuid5(DATASET_NAMESPACE, ":".join(str(part) for part in parts))


def build_workspace_plans(config: SyntheticConfig) -> tuple[WorkspacePlan, ...]:
    plans: list[WorkspacePlan] = []
    for index in range(config.workspaces):
        is_global = index % 3 == 2
        plans.append(
            WorkspacePlan(
                id=stable_uuid("workspace", index),
                index=index,
                name=f"Synthetic Marketing Lab {index + 1:02d}",
                currency_code="USD" if is_global else "KRW",
                timezone="America/Los_Angeles" if is_global else "Asia/Seoul",
            )
        )
    return tuple(plans)


def build_campaign_plans(config: SyntheticConfig) -> tuple[CampaignPlan, ...]:
    plans: list[CampaignPlan] = []
    global_index = 0
    for workspace in build_workspace_plans(config):
        for local_index in range(config.campaigns_per_workspace):
            rng = random.Random(config.seed + workspace.index * 100_003 + local_index)
            objective, goal, target_metrics = _OBJECTIVES[
                global_index % len(_OBJECTIVES)
            ]
            brand = _BRANDS[(global_index // 3) % len(_BRANDS)]
            product = _PRODUCTS[(global_index * 3 + workspace.index) % len(_PRODUCTS)]
            audience = _AUDIENCES[(global_index * 5 + local_index) % len(_AUDIENCES)]
            period_start = config.start_date + timedelta(
                days=(local_index % 12) * 14 + workspace.index * 7
            )
            platform_count = 1 + (global_index % 3)
            platform_order = ("GOOGLE_ADS", "META_ADS", "YOUTUBE")
            platform_offset = global_index % len(platform_order)
            platforms = tuple(
                platform_order[(platform_offset + offset) % len(platform_order)]
                for offset in range(platform_count)
            )
            budget = (
                rng.uniform(250.0, 2_500.0)
                if workspace.currency_code == "USD"
                else rng.uniform(250_000.0, 2_500_000.0)
            )
            plans.append(
                CampaignPlan(
                    id=stable_uuid("campaign", workspace.index, local_index),
                    workspace=workspace,
                    global_index=global_index,
                    name=(
                        f"[{brand}] {product} | {objective} | "
                        f"{period_start:%Y-%m} | C{global_index + 1:04d}"
                    ),
                    goal=f"{audience} 대상 {goal}",
                    start=period_start,
                    end=period_start + timedelta(days=config.days - 1),
                    target_metrics=target_metrics,
                    platforms=platforms,
                    pattern=_PATTERNS[global_index % len(_PATTERNS)],
                    daily_budget=round(budget, 2),
                    conversion_value=(
                        round(rng.uniform(35.0, 240.0), 2)
                        if workspace.currency_code == "USD"
                        else round(rng.uniform(35_000.0, 240_000.0), 0)
                    ),
                    quality=rng.uniform(0.78, 1.28),
                )
            )
            global_index += 1
    return tuple(plans)


def _pattern_factors(pattern: str, progress: float) -> tuple[float, float, float]:
    budget = ctr = cvr = 1.0
    if pattern == "growth":
        budget = 0.72 + 0.58 * progress
        ctr = 0.88 + 0.24 * progress
    elif pattern == "fatigue" and progress > 0.52:
        decay = (progress - 0.52) / 0.48
        ctr = 1.0 - 0.42 * decay
        cvr = 1.0 - 0.24 * decay
    elif pattern == "launch_spike":
        budget = 1.0 + 0.75 * exp(-progress * 12)
        ctr = 1.0 + 0.35 * exp(-progress * 10)
    elif pattern == "budget_cut" and progress > 0.65:
        budget = 0.48
    elif pattern == "midflight_recovery":
        dip = exp(-((progress - 0.48) ** 2) / 0.012)
        ctr = 1.0 - 0.38 * dip
        cvr = 1.0 - 0.28 * dip
    return budget, ctr, cvr


def build_platform_days(
    campaign: CampaignPlan,
    *,
    day_index: int,
    total_days: int,
    seed: int,
) -> tuple[PlatformDay, ...]:
    if not 0 <= day_index < total_days:
        raise ValueError("day_index must be inside the campaign period")
    day = campaign.start + timedelta(days=day_index)
    progress = day_index / max(total_days - 1, 1)
    pattern_budget, pattern_ctr, pattern_cvr = _pattern_factors(
        campaign.pattern, progress
    )
    weekend_factor = 0.86 if day.weekday() >= 5 else 1.0
    platform_budget = campaign.daily_budget / len(campaign.platforms)
    output: list[PlatformDay] = []

    for platform_index, surface in enumerate(campaign.platforms):
        rng = random.Random(
            seed + campaign.global_index * 1_000_003 + day_index * 101 + platform_index
        )
        baseline = _PLATFORM_BASELINES[surface]
        noise = rng.uniform(0.91, 1.09)
        spend = max(
            0.0,
            platform_budget * pattern_budget * weekend_factor * rng.uniform(0.92, 1.06),
        )
        currency_scale = 1.0 if campaign.workspace.currency_code == "KRW" else 0.001
        cpm = baseline["cpm"] * currency_scale * rng.uniform(0.88, 1.14)
        impressions = max(1, round(spend * 1_000 / cpm))
        ctr = min(
            0.35,
            baseline["ctr"] * campaign.quality * pattern_ctr * noise,
        )
        clicks = max(0, round(impressions * ctr))
        cvr = min(
            0.45,
            baseline["cvr"] * campaign.quality * pattern_cvr * rng.uniform(0.9, 1.1),
        )
        conversions = max(0, round(clicks * cvr))
        conversion_value = round(
            conversions * campaign.conversion_value * rng.uniform(0.92, 1.08), 2
        )
        spend = round(spend, 2)

        tracking_gap = (
            campaign.pattern == "tracking_gap"
            and total_days // 2 <= day_index < total_days // 2 + 3
            and platform_index == 0
        )
        currency_unit = f"currency:{campaign.workspace.currency_code}"
        metrics = [
            MetricDatum("impressions", float(impressions), "count"),
            MetricDatum("clicks", float(clicks), "count"),
            MetricDatum("spend", spend, currency_unit),
            MetricDatum(
                "ctr",
                round(clicks / impressions, 8),
                "ratio",
                "clicks / impressions",
            ),
        ]
        if surface == "META_ADS":
            metrics.append(
                MetricDatum("meta.reach", float(round(impressions * 0.72)), "count")
            )
        if surface == "YOUTUBE":
            metrics.append(
                MetricDatum(
                    "youtube.video_views",
                    float(round(impressions * rng.uniform(0.28, 0.55))),
                    "count",
                )
            )
        if not tracking_gap:
            metrics.extend(
                (
                    MetricDatum("conversions", float(conversions), "count"),
                    MetricDatum("conversion_value", conversion_value, currency_unit),
                    MetricDatum(
                        "cvr",
                        round(conversions / clicks, 8) if clicks else 0.0,
                        "ratio",
                        "conversions / clicks",
                    ),
                    MetricDatum(
                        "cpc",
                        round(spend / clicks, 4) if clicks else 0.0,
                        currency_unit,
                        "spend / clicks",
                    ),
                    MetricDatum(
                        "cpa",
                        round(spend / conversions, 4) if conversions else 0.0,
                        currency_unit,
                        "spend / conversions",
                    ),
                    MetricDatum(
                        "roas",
                        round(conversion_value / spend, 8) if spend else 0.0,
                        "ratio",
                        "conversion_value / spend",
                    ),
                )
            )

        platform_slug = surface.lower().replace("_", "-")
        output.append(
            PlatformDay(
                surface=surface,
                account_ref=f"synthetic-account:{campaign.workspace.index}:{platform_slug}",
                external_campaign_ref=(
                    f"SYN-{surface[:3]}-{campaign.global_index + 1:06d}"
                ),
                connector=f"synthetic-{platform_slug}-v1",
                attribution_setting=(
                    "7d_click+1d_view" if surface == "META_ADS" else "30d_click"
                ),
                metrics=tuple(metrics),
                missing_reason=(
                    f"synthetic conversion tracking gap on {surface}"
                    if tracking_gap
                    else None
                ),
            )
        )
    return tuple(output)


def build_campaign_documents(campaign: CampaignPlan) -> tuple[DocumentPlan, ...]:
    observation, recommendation = _PATTERN_DOCUMENT_FACTS[campaign.pattern]
    code = f"C{campaign.global_index + 1:04d}"
    common_sections = [
        (
            f"## 운영 기록 {index:02d}\n"
            f"{code}의 목표 고객과 매체 운영 범위를 확인했습니다. "
            f"보고 기준은 {campaign.workspace.timezone}이며 비용 단위는 "
            f"{campaign.workspace.currency_code}입니다. 데이터는 동일 기간과 "
            "동일 지표 정의로 비교하고 단기 변동만으로 원인을 확정하지 않습니다."
        )
        for index in range(1, 19)
    ]
    document_specs = (
        (
            "BRIEF",
            f"{code} 캠페인 실행 브리프",
            (
                f"페이싱 원칙: 일 예산 {campaign.daily_budget:.2f} "
                f"{campaign.workspace.currency_code}를 기준으로 주간 소진율 "
                "90~110%를 정상 범위로 관리합니다. "
                f"핵심 목표는 {campaign.goal}입니다."
            ),
        ),
        (
            "MEMO",
            f"{code} 주간 운영 메모",
            f"핵심 관찰: {observation}",
        ),
        (
            "ANALYSIS",
            f"{code} 성과 분석 및 권고",
            f"권고 근거: {recommendation}",
        ),
    )
    output = []
    for document_index, (document_type, title, gold_line) in enumerate(document_specs):
        insertion_index = 4 + (campaign.global_index + document_index * 5) % 11
        sections = list(common_sections)
        sections.insert(insertion_index, f"## 핵심 근거\n{gold_line}")
        content = (
            f"# {title}\n\n"
            f"캠페인: {campaign.name}\n"
            f"기간: {campaign.start.isoformat()} ~ {campaign.end.isoformat()}\n"
            f"플랫폼: {', '.join(campaign.platforms)}\n\n"
            + "\n\n".join(sections)
            + "\n"
        )
        source_ref = f"{DATASET_NAME}:document:{code.lower()}:{document_type.lower()}"
        output.append(
            DocumentPlan(
                id=stable_uuid("document", campaign.id, document_type),
                campaign_id=campaign.id,
                workspace_id=campaign.workspace.id,
                document_type=document_type,
                title=title,
                content=content,
                source_ref=source_ref,
                created_at=datetime.combine(
                    campaign.start + timedelta(days=7 + document_index),
                    datetime.min.time(),
                    UTC,
                ),
            )
        )
    return tuple(output)


class SyntheticPostgresSeeder:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def seed(
        self,
        config: SyntheticConfig,
        *,
        replace: bool = False,
        show_progress: bool = True,
    ) -> SeedSummary:
        plans = build_campaign_plans(config)
        summary = SeedSummary()
        with self._database.connect() as connection:
            existing = connection.execute(
                "SELECT 1 FROM users WHERE id = %s",
                (stable_uuid("user"),),
            ).fetchone()
            if existing is not None:
                if not replace:
                    raise RuntimeError(
                        "synthetic dataset already exists; rerun with --replace"
                    )
                self._delete_existing(connection)
            self._insert_identity(connection, config)

            grouped: dict[UUID, list[CampaignPlan]] = {}
            for plan in plans:
                grouped.setdefault(plan.workspace.id, []).append(plan)

            processed = 0
            for workspace_plans in grouped.values():
                self._insert_workspace(connection, workspace_plans[0].workspace)
                summary.workspaces += 1
                for plan in workspace_plans:
                    self._insert_campaign(connection, plan, config)
                    self._insert_campaign_observations(
                        connection, plan, config, summary
                    )
                    summary.documents += self._insert_campaign_documents(
                        connection, plan
                    )
                    summary.campaigns += 1
                    processed += 1
                    if show_progress and (
                        processed % 25 == 0 or processed == len(plans)
                    ):
                        print(
                            f"seeded {processed}/{len(plans)} campaigns",
                            file=sys.stderr,
                        )
        return summary

    @staticmethod
    def _delete_existing(connection: Connection[dict[str, object]]) -> None:
        user_id = stable_uuid("user")
        workspace_rows = connection.execute(
            """SELECT wm.workspace_id
            FROM workspace_memberships wm
            JOIN workspaces w ON w.id = wm.workspace_id
            WHERE wm.user_id = %s
              AND w.name LIKE 'Synthetic Marketing Lab %%'""",
            (user_id,),
        ).fetchall()
        workspace_ids = [row["workspace_id"] for row in workspace_rows]
        if workspace_ids:
            connection.execute(
                "DELETE FROM workspaces WHERE id = ANY(%s)", (workspace_ids,)
            )
        connection.execute("DELETE FROM users WHERE id = %s", (user_id,))

    @staticmethod
    def _insert_identity(
        connection: Connection[dict[str, object]], config: SyntheticConfig
    ) -> None:
        created_at = datetime.combine(config.start_date, datetime.min.time(), UTC)
        connection.execute(
            """INSERT INTO users(
                id, google_subject, email, display_name, created_at
            ) VALUES (%s, %s, %s, %s, %s)""",
            (
                stable_uuid("user"),
                DATASET_NAME,
                "synthetic-marketing@launchpilot.invalid",
                "Synthetic Marketing Evaluator",
                created_at,
            ),
        )

    @staticmethod
    def _insert_workspace(
        connection: Connection[dict[str, object]], workspace: WorkspacePlan
    ) -> None:
        created_at = datetime(2025, 1, 1, tzinfo=UTC) + timedelta(
            minutes=workspace.index
        )
        connection.execute(
            "INSERT INTO workspaces(id, name, created_at) VALUES (%s, %s, %s)",
            (workspace.id, workspace.name, created_at),
        )
        connection.execute(
            """INSERT INTO workspace_memberships(
                workspace_id, user_id, role, created_at
            ) VALUES (%s, %s, %s, %s)""",
            (workspace.id, stable_uuid("user"), "OWNER", created_at),
        )

    @staticmethod
    def _insert_campaign(
        connection: Connection[dict[str, object]],
        plan: CampaignPlan,
        config: SyntheticConfig,
    ) -> None:
        created_at = datetime.combine(plan.start, datetime.min.time(), UTC)
        connection.execute(
            """INSERT INTO campaigns(
                id, workspace_id, name, goal, period_start, period_end,
                target_metrics, resource_bindings, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                plan.id,
                plan.workspace.id,
                plan.name,
                plan.goal,
                plan.start,
                plan.end,
                Jsonb(list(plan.target_metrics)),
                Jsonb([]),
                created_at,
            ),
        )

    @staticmethod
    def _insert_campaign_observations(
        connection: Connection[dict[str, object]],
        plan: CampaignPlan,
        config: SyntheticConfig,
        summary: SeedSummary,
    ) -> None:
        observation_rows: list[tuple[object, ...]] = []
        slice_rows: list[tuple[object, ...]] = []
        metric_rows: list[tuple[object, ...]] = []
        for day_index in range(config.days):
            day = plan.start + timedelta(days=day_index)
            observation_id = stable_uuid("observation", plan.id, day)
            slices = build_platform_days(
                plan,
                day_index=day_index,
                total_days=config.days,
                seed=config.seed,
            )
            missing_reasons = tuple(
                item.missing_reason for item in slices if item.missing_reason
            )
            observation_rows.append(
                (
                    observation_id,
                    plan.id,
                    day,
                    day,
                    "PARTIAL" if missing_reasons else "COMPLETE",
                    Jsonb(list(missing_reasons)),
                    datetime.combine(day + timedelta(days=1), datetime.min.time(), UTC),
                )
            )
            summary.observations += 1
            if missing_reasons:
                summary.partial_observations += 1

            for slice_index, platform_day in enumerate(slices):
                slice_rows.append(
                    (
                        observation_id,
                        slice_index,
                        platform_day.surface,
                        platform_day.connector,
                        platform_day.account_ref,
                        f"{DATASET_NAME}:{plan.id}:{day}:{platform_day.surface}",
                        platform_day.external_campaign_ref,
                        plan.workspace.currency_code,
                        plan.workspace.timezone,
                        platform_day.attribution_setting,
                    )
                )
                summary.platform_slices += 1
                provenance = (
                    f"{DATASET_NAME}:{config.seed}:{plan.id}:"
                    f"{day}:{platform_day.surface}"
                )
                subject_ref = (
                    f"{platform_day.surface.lower()}-campaign:"
                    f"{platform_day.external_campaign_ref}"
                )
                for metric_index, metric in enumerate(platform_day.metrics):
                    metric_rows.append(
                        (
                            observation_id,
                            slice_index,
                            metric_index,
                            subject_ref,
                            "CAMPAIGN",
                            metric.key,
                            metric.value,
                            metric.unit,
                            day,
                            day,
                            provenance,
                            metric.calculation,
                        )
                    )
                    summary.metrics += 1

        cursor = connection.cursor()
        cursor.executemany(
            """INSERT INTO campaign_observations(
                id, campaign_id, period_start, period_end, completeness_status,
                missing_reasons, captured_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            observation_rows,
        )
        cursor.executemany(
            """INSERT INTO platform_slices(
                observation_id, slice_index, surface, connector, account_ref,
                fetch_run_ref, external_campaign_ref, currency_code, timezone,
                attribution_setting
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            slice_rows,
        )
        cursor.executemany(
            """INSERT INTO metric_observations(
                observation_id, slice_index, metric_index, subject_ref,
                subject_level, metric_key, value, unit, period_start, period_end,
                provenance_ref, calculation
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            metric_rows,
        )

    @staticmethod
    def _insert_campaign_documents(
        connection: Connection[dict[str, object]], plan: CampaignPlan
    ) -> int:
        documents = build_campaign_documents(plan)
        connection.cursor().executemany(
            """INSERT INTO campaign_documents(
                id, campaign_id, workspace_id, document_type, title, content,
                source_ref, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            [
                (
                    document.id,
                    document.campaign_id,
                    document.workspace_id,
                    document.document_type,
                    document.title,
                    document.content,
                    document.source_ref,
                    document.created_at,
                )
                for document in documents
            ],
        )
        return len(documents)


def _config_from_args(args: argparse.Namespace) -> SyntheticConfig:
    return SyntheticConfig(
        workspaces=args.workspaces,
        campaigns_per_workspace=args.campaigns_per_workspace,
        days=args.days,
        start_date=date.fromisoformat(args.start_date),
        seed=args.seed,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Seed deterministic synthetic marketing data into PostgreSQL."
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv(
            "DATABASE_URL",
            "postgresql://launchpilot:launchpilot-local@localhost:5432/launchpilot",
        ),
    )
    parser.add_argument("--workspaces", type=int, default=3)
    parser.add_argument("--campaigns-per-workspace", type=int, default=100)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--start-date", default="2025-01-01")
    parser.add_argument("--seed", type=int, default=20260813)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace only data owned by the synthetic dataset user.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned scale without connecting to PostgreSQL.",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = _config_from_args(args)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "dataset": DATASET_NAME,
                    "workspaces": config.workspaces,
                    "campaigns": config.campaign_count,
                    "observations": config.observation_count,
                    "days_per_campaign": config.days,
                    "seed": config.seed,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    database = PostgresDatabase(args.database_url)
    summary = SyntheticPostgresSeeder(database).seed(config, replace=args.replace)
    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
