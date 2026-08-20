from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True, slots=True)
class CausalChainBundle:
    campaign_code: str
    seed_node_key: str
    triggering_facts: list[dict[str, Any]]
    guiding_briefs: list[dict[str, Any]]
    action_memo: dict[str, Any] | None
    evaluating_analyses: list[dict[str, Any]]
    causal_explanation: str

@dataclass(frozen=True, slots=True)
class GraphTraversalResult:
    campaign_id: str
    campaign_code: str
    campaign_name: str
    connected_documents: list[dict[str, Any]]
    connected_metrics: list[dict[str, Any]]
    causal_chains: list[CausalChainBundle]
    multi_hop_summary: str

class MarketingKnowledgeGraph:
    def __init__(self, db_conn: sqlite3.Connection) -> None:
        self._conn = db_conn

    def traverse(self, query: str, campaign_identifier: str | None = None) -> GraphTraversalResult | None:
        cur = self._conn.cursor()
        if campaign_identifier:
            row = cur.execute(
                "SELECT id, campaign_code, name FROM campaigns WHERE campaign_code = ? OR id = ? LIMIT 1",
                (campaign_identifier, campaign_identifier),
            ).fetchone()
        else:
            row = cur.execute("SELECT id, campaign_code, name FROM campaigns LIMIT 1").fetchone()

        if not row:
            return None

        c_id, c_code, c_name = row
        doc_rows = cur.execute(
            "SELECT id, document_key, title, document_type, published_on, content FROM campaign_documents WHERE campaign_id = ? ORDER BY published_on ASC",
            (c_id,),
        ).fetchall()

        doc_dict = {
            r[1]: {
                "id": r[0],
                "document_key": r[1],
                "title": r[2],
                "document_type": r[3],
                "published_on": r[4],
                "excerpt": r[5][:300],
                "content": r[5],
            }
            for r in doc_rows
        }

        metric_rows = cur.execute(
            "SELECT id, channel, date, spend, impressions, clicks, conversions, roas, attribution_window FROM metric_observations WHERE campaign_id = ? ORDER BY date DESC LIMIT 30",
            (c_id,),
        ).fetchall()

        connected_metrics = [
            {
                "id": r[0],
                "channel": r[1],
                "date": r[2],
                "spend": r[3],
                "impressions": r[4],
                "clicks": r[5],
                "conversions": r[6],
                "roas": r[7],
                "attribution_window": r[8],
            }
            for r in metric_rows
        ]

        edge_rows = cur.execute(
            "SELECT source_node_key, source_node_type, target_node_key, target_node_type, relation_type, description FROM graph_edges WHERE campaign_id = ?",
            (c_id,),
        ).fetchall()

        memo_incoming_triggers = {}
        memo_incoming_guides = {}
        memo_outgoing_evals = {}

        for src_key, src_type, tgt_key, tgt_type, rel, desc in edge_rows:
            if rel == "TRIGGERS_ACTION":
                memo_incoming_triggers[tgt_key] = {"fact_key": src_key, "desc": desc}
            elif rel == "GUIDES_EXECUTION":
                memo_incoming_guides[tgt_key] = {"brief_key": src_key, "desc": desc}
            elif rel == "DIAGNOSED_BY":
                if src_key not in memo_outgoing_evals:
                    memo_outgoing_evals[src_key] = []
                memo_outgoing_evals[src_key].append({"analysis_key": tgt_key, "desc": desc})

        causal_chains = []
        for d_key, doc_data in doc_dict.items():
            if doc_data["document_type"] == "MEMO":
                trigger = memo_incoming_triggers.get(d_key)
                guide = memo_incoming_guides.get(d_key)
                evals = memo_outgoing_evals.get(d_key, [])
                if trigger or guide or evals:
                    trigger_list = [trigger] if trigger else []
                    guide_list = [doc_dict[guide["brief_key"]]] if (guide and guide["brief_key"] in doc_dict) else []
                    eval_list = [doc_dict[e["analysis_key"]] for e in evals if e["analysis_key"] in doc_dict]
                    explanation = f"[{c_code}] "
                    if trigger:
                        explanation += f"원인({trigger['desc']}) -> "
                    explanation += f"조치({doc_data['title']}) -> "
                    if eval_list:
                        explanation += f"후속 진단({', '.join(e['title'] for e in eval_list)})"
                    causal_chains.append(
                        CausalChainBundle(
                            campaign_code=c_code,
                            seed_node_key=d_key,
                            triggering_facts=trigger_list,
                            guiding_briefs=guide_list,
                            action_memo=doc_data,
                            evaluating_analyses=eval_list,
                            causal_explanation=explanation,
                        )
                    )

        summary = f"캠페인 {c_code}({c_name}): {len(doc_dict)}개 문서, {len(connected_metrics)}개 Fact, {len(causal_chains)}개 다단계 인과 경로 연결 완료"
        return GraphTraversalResult(
            campaign_id=c_id,
            campaign_code=c_code,
            campaign_name=c_name,
            connected_documents=list(doc_dict.values()),
            connected_metrics=connected_metrics,
            causal_chains=causal_chains,
            multi_hop_summary=summary,
        )