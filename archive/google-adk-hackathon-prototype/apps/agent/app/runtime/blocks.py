"""Builds + appends contract-shaped block messages to a ThreadRecord.

Every message carries a monotonic `sequence` so the WS endpoint can replay.
The agent emits the same block vocabulary the frontend renders (contract 01/02):
text, activity, markdown_document, artifact, approval, result, error.

Block dicts are user-safe: never raw chain-of-thought, raw Gemini chunks, or
MCP/Elastic transport frames (contract 02 README).
"""
from __future__ import annotations

from typing import Any, Optional

from app.contracts import InternalStreamMessage, StreamRole
from app.ids import message_id, now_iso
from app.runtime.thread_store import ThreadRecord


async def commit(
    record: ThreadRecord,
    role: StreamRole,
    blocks: list[dict],
) -> InternalStreamMessage:
    # Single choke point for every outbound message: assigns the sequence,
    # stamps the time, and appends (which notifies WS streamers).
    message = InternalStreamMessage(
        id=message_id(),
        thread_id=record.thread_id,
        sequence=record.next_sequence(),
        role=role,
        created_at=now_iso(),
        blocks=blocks,
    )
    await record.append(message)
    return message


async def assistant(record: ThreadRecord, blocks: list[dict]) -> InternalStreamMessage:
    return await commit(record, StreamRole.assistant, blocks)


async def system(record: ThreadRecord, blocks: list[dict]) -> InternalStreamMessage:
    return await commit(record, StreamRole.system, blocks)


# --- block builders (contract 01 MessageBlock shapes) ---
def text_block(text: str) -> dict:
    return {"kind": "text", "text": text}


def activity_block(activity_id: str, title: str, status: str, detail: Optional[str] = None) -> dict:
    # status in queued | running | done | failed
    block: dict = {"kind": "activity", "id": activity_id, "title": title, "status": status}
    if detail is not None:
        block["detail"] = detail
    return block


def markdown_document_block(doc_id: str, title: str, markdown: str, summary: Optional[str] = None) -> dict:
    block: dict = {"kind": "markdown_document", "id": doc_id, "title": title, "markdown": markdown}
    if summary is not None:
        block["summary"] = summary
    return block


def artifact_block(artifact_id: str, artifact_kind: str, title: str, content: Any) -> dict:
    # artifact_kind in signal | hypothesis | experiment_plan | growth_brief | generic
    return {"kind": "artifact", "id": artifact_id, "artifact_kind": artifact_kind, "title": title, "content": content}


def approval_block(approval_id: str, title: str, target_id: str, payload: Any) -> dict:
    # Java's captureApprovalGate keys off kind=="approval" + the payload field.
    return {
        "kind": "approval",
        "id": approval_id,
        "title": title,
        "target_id": target_id,
        "actions": ["approve", "reject", "request_changes"],
        "payload": payload,
    }


def result_block(title: str, detail: Optional[str] = None) -> dict:
    block: dict = {"kind": "result", "title": title}
    if detail is not None:
        block["detail"] = detail
    return block


def error_block(title: str, detail: str, retryable: bool = True) -> dict:
    return {"kind": "error", "title": title, "detail": detail, "retryable": retryable}
