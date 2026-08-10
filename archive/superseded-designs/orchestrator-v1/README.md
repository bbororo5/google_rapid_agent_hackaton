# Orchestrator v1 Archive

These documents describe the pre-ADR-004 orchestrator design.

They are archived because Python Agent Core v2 changed the orchestration model:

- from router-style turn classification to `StateDeltaProposal -> reducer -> delegation`
- from process-only agent working memory to Elastic-backed runtime state
- from "pre-approval candidates are never stored" to "pre-approval candidates are
  not business documents, but runtime-only TTL snapshots/refs are allowed"
- from CSV/data-upload centered steering to campaign-scoped working context

Use the current documents instead:

- `docs/architecture/adr/05-state-reactive-workflow.md`
- `docs/architecture/agent-core-v2-design.md`
- `contracts/07-agent-runtime-elastic/README.md`
