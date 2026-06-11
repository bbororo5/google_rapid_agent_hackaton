"""Quality evaluation runner (Part B2/B4).

For each scenario: drive the orchestrator like the turn API would (reuse the
test_golden_path pattern), pull the final AgentResultPayload off the approval
block, compute free deterministic metrics, score quality with the LLM judge
(real-LLM mode only), attach an EVALUATOR span to the same Phoenix trace, and
write a JSON + Markdown report.

Run:
    cd apps/agent
    PYTHONPATH=. uv run --with-editable . python -m app.eval.run_eval
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app import orchestrator, tracing
from app.agents import reviewer
from app.config import get_settings
from app.contracts import AgentResultPayload
from app.observability import init_tracing
from app.runtime.thread_store import ThreadStore
from app.tools import evidence

_HERE = Path(__file__).resolve().parent
_DATASET = _HERE / "dataset" / "scenarios.json"
_REPORT_DIR = _HERE / "report"


def _extract_payload(record) -> AgentResultPayload | None:
    # The pipeline ends with an approval block carrying the full payload.
    for m in record.messages:
        for b in m.blocks:
            if b.get("kind") == "approval" and "payload" in b:
                return AgentResultPayload.model_validate(b["payload"])
    return None


def _deterministic_metrics(payload: AgentResultPayload, grounding: dict | None = None) -> dict:
    # Free metrics straight from the run -- no LLM. The same checks the reviewer
    # gate applies (including the grounding gate when a capture is available),
    # plus a signal-strength breakdown vs the configured thresholds.
    s = get_settings()
    report = reviewer.review(payload, grounding)

    def _bucket(lift: float) -> str:
        if lift >= s.signal_threshold_high:
            return "strong"
        if lift >= s.signal_threshold_low:
            return "weak"
        return "noise"

    buckets = {"strong": 0, "weak": 0, "noise": 0}
    for sig in payload.signals:
        buckets[_bucket(sig.lift_ratio)] += 1

    return {
        "reviewer_passed": report.passed,
        "issue_codes": [i.code.value for i in report.issues],
        "n_signals": len(payload.signals),
        "n_hypotheses": len(payload.hypotheses),
        "n_experiments": len(payload.experiment_plan.items),
        "signal_strength": buckets,
    }


async def _run_scenario(scenario: dict, use_judge: bool) -> dict:
    store = ThreadStore()
    thread_id = f"thread_{scenario['id']}"
    record = store.get_or_create(thread_id)
    record.set_context(scenario.get("workspace_id"), scenario.get("campaign_id"))

    result: dict = {"id": scenario["id"], "question": scenario["question"],
                    "mode": scenario.get("mode")}

    # Wrap the whole scenario in one CHAIN span so the pipeline trace + the judge
    # EVALUATOR span land in the same Phoenix trace.
    with tracing.chain_span(
        "launchpilot.eval.scenario",
        input_value=scenario["question"],
        metadata={"scenario_id": scenario["id"], "mode": scenario.get("mode")},
        workspace_id=scenario.get("workspace_id"),
        campaign_id=scenario.get("campaign_id"),
    ):
        # Outer capture: the orchestrator's inner evidence.capture() reuses this
        # object, so the tool ground truth survives the turn and feeds the judge.
        with evidence.capture() as grounding:
            try:
                await orchestrator.process_turn(record, scenario["question"])
            except Exception as exc:  # noqa: BLE001 - record the failure, keep going
                result["error"] = f"{type(exc).__name__}: {exc}"
                return result

        payload = _extract_payload(record)
        if payload is None:
            result["error"] = "no approval payload (router chose chat or validation failed)"
            return result

        result["metrics"] = _deterministic_metrics(payload, grounding.snapshot())

        if use_judge:
            from app.eval import judge as judge_mod

            scores = await judge_mod.judge(payload, grounding.snapshot())
            result["quality"] = scores.model_dump(mode="json")
            # EVALUATOR span: LLM-as-a-judge quality summary (contract 06).
            with tracing.evaluator_span(
                "launchpilot.quality.judge",
                input_value={"scenario_id": scenario["id"]},
                output_value=scores.model_dump(mode="json"),
                metadata={"scenario_id": scenario["id"],
                          "overall": scores.overall},
                workspace_id=scenario.get("workspace_id"),
                campaign_id=scenario.get("campaign_id"),
            ):
                pass
    return result


def _write_report(results: list[dict]) -> None:
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / "eval_report.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = ["# LaunchPilot 분석 퀄리티 리포트", ""]
    lines.append("| scenario | mode | reviewer | sig(S/W/N) | H | E | signal | hyp | plan | overall |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        if r.get("error"):
            lines.append(f"| {r['id']} | {r.get('mode','')} | ERROR | - | - | - | - | - | - | {r['error']} |")
            continue
        m = r["metrics"]
        b = m["signal_strength"]
        sig_b = f"{b['strong']}/{b['weak']}/{b['noise']}"
        q = r.get("quality")
        if q:
            sv, hg, pa = q["signal_validity"]["score"], q["hypothesis_grounding"]["score"], q["plan_actionability"]["score"]
            ov = q["overall"]
        else:
            sv = hg = pa = ov = "-"
        rev = "PASS" if m["reviewer_passed"] else "FAIL"
        lines.append(
            f"| {r['id']} | {r.get('mode','')} | {rev} | {sig_b} | "
            f"{m['n_hypotheses']} | {m['n_experiments']} | {sv} | {hg} | {pa} | {ov} |"
        )

    # Per-axis rationale detail.
    lines += ["", "## 심판 코멘트", ""]
    for r in results:
        q = r.get("quality")
        if not q:
            continue
        lines.append(f"### {r['id']} (overall {q['overall']}) — {q['summary']}")
        for axis in ("signal_validity", "hypothesis_grounding", "plan_actionability"):
            lines.append(f"- **{axis}** {q[axis]['score']}/5: {q[axis]['rationale']}")
        lines.append("")

    (_REPORT_DIR / "eval_report.md").write_text("\n".join(lines), encoding="utf-8")


async def main() -> None:
    init_tracing()  # turn on Phoenix export if PHOENIX_API_KEY is set (else no-op)
    s = get_settings()
    use_judge = s.use_real_llm
    scenarios = json.loads(_DATASET.read_text(encoding="utf-8"))
    print(f"eval: {len(scenarios)} scenarios | llm={'gemini' if s.use_real_llm else 'stub'} "
          f"| judge={'on' if use_judge else 'off (stub mode)'}")

    results = []
    for sc in scenarios:
        print(f"  - {sc['id']} ...", flush=True)
        results.append(await _run_scenario(sc, use_judge))

    _write_report(results)
    print(f"report written: {_REPORT_DIR / 'eval_report.md'}")


if __name__ == "__main__":
    asyncio.run(main())
