"""계획 라운드: 가설을 다음 주 실험 계획으로 만들고, 승인 관문을 연다."""
from __future__ import annotations

from app import telemetry
from app.agents import formatter, reviewer, workers
from app.contracts import Hypothesis, Signal
from app.ids import approval_id
from app.orchestration.models import TurnContext, TurnOutcome
from app.orchestration.phases.base import BasePhaseRunner, log
from app.orchestration.phases.windows import analysis_window
from app.runtime import blocks
from app.runtime.episode_query import recent_episode_context
from app.runtime.state import PhaseType


class PlanRoundRunner(BasePhaseRunner):
    """계획 라운드: 가설을 다음 주 실험 계획으로 만들고, 승인 관문을 연다."""

    phase = PhaseType.EXPERIMENT_PLAN

    async def run(self, turn: TurnContext) -> TurnOutcome:
        # 목표: 가설을 실험 계획으로 만들고, 가드레일을 통과하면 승인을 요청한다.
        #       앞 단계 재료(신호+가설)가 없으면 먼저 하라고 요청하고 끝낸다.
        self.stop_if_cancelled(turn)                       # 취소됐으면 중단한다
        self.enter_phase(turn)                             # 계획 단계로 진입한다
        signals = self.load_analysis_signals(turn)         # 재료 1: 분석 신호를 불러온다
        hypotheses = self.load_drafted_hypotheses(turn)    # 재료 2: 가설을 불러온다
        if not signals or not hypotheses:
            return await self._require_hypotheses_first(turn)  # 재료 없으면 앞 단계부터 요청

        plan = await self._draft_plan(turn, signals, hypotheses)  # 계획을 작성한다
        await self._save_plan(turn, plan)                         # 계획을 저장한다

        review_payload = formatter.assemble(signals, hypotheses, plan)
        report = await self._review_plan(turn, signals, hypotheses, plan, review_payload)  # 가드레일 검토
        if not report.passed:
            return await self._report_validation_failed(turn, report)  # 막히면 사유 알리고 끝

        return await self._request_approval(turn, plan, review_payload)  # 통과 시 승인 요청

    async def _require_hypotheses_first(self, turn: TurnContext) -> TurnOutcome:
        # 신호나 가설이 없으면 앞 라운드를 먼저 하라고 안내하고 끝낸다.
        await self.emitter.system_error(
            turn.record,
            "Hypotheses required",
            "Complete the analysis and hypothesis rounds before drafting an experiment plan.",
        )
        return TurnOutcome({"phase": self.phase.value, "status": "missing_hypotheses"})

    async def _draft_plan(self, turn: TurnContext, signals: list[Signal], hypotheses: list[Hypothesis]):
        # 작성자(Gemini)를 불러 가설로부터 다음 주 실험 계획을 만든다.
        log.info("[plan] writer start")
        await self.emitter.progress(
            turn.record,
            "plan.load_context",
            "Loaded signals and hypotheses for planning",
            "done",
            f"{len(signals)} signal(s), {len(hypotheses)} hypothesis(es)",
        )
        memory_context = await recent_episode_context(
            turn.repository, turn.record.state.scope, self.phase
        )
        async with self.emitter.activity(
            turn.record,
            "plan.draft",
            "Drafting experiment plan with Gemini",
            "Drafted experiment plan",
        ):
            plan = (
                await workers.run_writer(turn.content, analysis_window(), hypotheses, memory_context)
            ).experiment_plan
        return plan

    async def _save_plan(self, turn: TurnContext, plan) -> None:
        # 계획을 상태 + 저장소에 보관하고(공통 헬퍼), 활성 아티팩트로 표시한다.
        turn.record.state.active_artifact_id = plan.id
        await self._save_round_result(
            turn,
            key="experiment_plan",
            payload=plan.model_dump(mode="json"),
            progress_id="artifact.save.plan",
            saving_title="Saving experiment plan artifact",
            saved_title="Saved experiment plan artifact",
            detail=plan.id,
        )
        log.info("[plan] writer done: %d item(s)", len(plan.items))

    async def _review_plan(self, turn: TurnContext, signals, hypotheses, plan, review_payload):
        # 승인 가드레일을 통과하는지 검사한다 (트레이스 span으로 감쌈).
        await self.emitter.progress(turn.record, "plan.review", "Checking approval guardrails", "running")
        guardrail_metadata = {
            "thread_id": turn.record.thread_id,
            "workspace_id": turn.record.workspace_id,
            "campaign_id": turn.record.campaign_id,
        }
        with telemetry.guardrail_span(
            input_value={"signals": len(signals), "hypotheses": len(hypotheses), "items": len(plan.items)},
            metadata={**guardrail_metadata, "validator_passed": None, "backtrack_count": 0},
            workspace_id=turn.record.workspace_id,
            campaign_id=turn.record.campaign_id,
        ) as guardrail_span:
            report = reviewer.review(review_payload)
            telemetry.record_guardrail_result(guardrail_span, report, guardrail_metadata)
        log.info("[plan] reviewer passed=%s issues=%d", report.passed, len(report.issues))
        return report

    async def _report_validation_failed(self, turn: TurnContext, report) -> TurnOutcome:
        # 가드레일 실패: 무엇이 막혔는지 알리고 승인 없이 끝낸다.
        await self.emitter.progress(
            turn.record,
            "plan.review",
            "Approval guardrails failed",
            "failed",
            f"{len(report.issues)} issue(s)",
        )
        await self.emitter.system_error(
            turn.record,
            "Validation failed",
            "; ".join(issue.message for issue in report.issues),
        )
        return TurnOutcome({"phase": self.phase.value, "validator_passed": False})

    async def _request_approval(self, turn: TurnContext, plan, review_payload) -> TurnOutcome:
        # 가드레일 통과: 계획 초안과 승인 버튼을 사용자에게 보낸다.
        await self.emitter.progress(turn.record, "plan.review", "Approval guardrails passed", "done")
        pending_approval_id = approval_id()
        turn.record.state.pending_approval_id = pending_approval_id
        await self.emitter.assistant_blocks(
            turn.record,
            [
                blocks.text_block("The experiment plan draft is ready. Please review and approve."),
                blocks.artifact_block(
                    plan.id, "experiment_plan", plan.summary, plan.model_dump(mode="json")
                ),
            ],
        )
        await self.emitter.assistant_blocks(
            turn.record,
            [
                blocks.approval_block(
                    pending_approval_id,
                    "Approve experiment plan",
                    plan.id,
                    review_payload.model_dump(mode="json"),
                )
            ],
        )
        log.info("plan round done thread=%s approval emitted plan=%s", turn.record.thread_id, plan.id)
        return TurnOutcome(
            {
                "phase": self.phase.value,
                "plan_id": plan.id,
                "experiments": len(plan.items),
                "validator_passed": True,
            }
        )
