# Agent Loop Autonomy Improvement Plan

Status: Initial runtime path implemented  
Date: 2026-06-12  
Related docs:
- `docs/architecture/agent-core-v2-design.md`
- `docs/architecture/adr/05-state-reactive-workflow.md`

Implementation note: the foreground `GoalController`, dynamic budget profiles,
`AgentLoop`, and `ConversationAdvisor` path are now wired into the Python Agent
Core. Long-running background execution is still a follow-up runtime capability
because it needs durable job ownership and UI resume semantics.

## 1. Problem

The current Python Agent Core behaves like a round-based workflow dispatcher, not
like a goal-seeking coding agent.

Current shape:

```text
user turn
-> load context
-> interpret intent
-> route once
-> run one phase or direct reply
-> commit state
-> stop
```

This is stable, but it makes the agent feel passive:

- It answers one turn at a time instead of pursuing a user goal until completion.
- Direct chat can be shallow because the Turn Interpreter may provide the reply.
- Phase workers create artifacts, but no separate advisor turns artifacts into a
  proactive explanation and next-step strategy.
- There is no loop that checks whether the response is sufficient, repairs weak
  outputs, or continues working when the user's goal clearly needs more work.
- The UI shows many "tool checks", but those are mostly pipeline events, not a
  visible agent deliberation loop.

The recent change to pass full conversation transcript, live block timeline, and
full phase artifacts into the interpreter is necessary context plumbing, but it
does not by itself create autonomy. Autonomy requires a runtime loop.

## 2. Target Behavior

The agent should dynamically scale its work to the user's request.

Small request:

```text
User: "What does hypothesis 2 mean?"
Agent: one advisor response, grounded in the hypothesis artifact, then stop.
```

Larger request:

```text
User: "Explain the first analysis in a way my team can understand, with concrete
next steps."
Agent:
1. loads full context and artifacts
2. identifies the explanation goal
3. drafts an explanation
4. checks if every signal is covered
5. adds practical next-step options
6. emits the response and stops
```

Workflow request:

```text
User: "Let's use hypothesis 2 and make a plan."
Agent:
1. resolves selected hypothesis from conversation and artifacts
2. runs the planning phase
3. validates the plan
4. repairs or retries if validation fails and budget remains
5. emits the plan artifact and approval gate
6. summarizes why this plan follows from hypothesis 2
```

The key difference is not answer length. The key difference is:

```text
goal -> plan -> act -> observe -> critique -> continue or stop
```

## 3. Architectural Direction

Keep the existing macro graph and deterministic reducer. Add a loop layer above
the router/phase runners.

Proposed shape:

```text
TurnWorkflow
-> TurnContextLoader
-> TurnInterpreter
-> GoalController
-> AgentLoop
   -> Planner
   -> ActionExecutor
   -> Observer
   -> Critic
   -> StopPolicy
-> StateCommitter
-> Checkpointer
```

The LLM still must not become the authority for workflow state. It may propose
actions and judge completeness, but deterministic code keeps these boundaries:

- phase eligibility
- approval gate ownership
- artifact validation
- retry limits
- cancellation
- state commit/revision rules

## 4. New Components

### 4.1 GoalController

Converts a user turn and reducer decision into a concrete per-turn goal.

Example fields:

```python
class TurnGoal(BaseModel):
    goal_id: str
    kind: Literal[
        "answer_question",
        "explain_artifacts",
        "run_phase",
        "revise_artifact",
        "approve_plan",
        "clarify"
    ]
    user_request: str
    target_phase: PhaseType | None
    selected_artifact_ids: list[str]
    requested_depth: Literal["brief", "normal", "deep"]
    run_mode: Literal["foreground", "background"]
    budget_profile: Literal[
        "interactive_quick",
        "standard_analysis",
        "deep_analysis",
        "background_research",
    ]
    completion_criteria: list[str]
    budgets: GoalBudget
```

Example completion criteria:

- "Answer the user's direct question."
- "Reference every relevant signal artifact."
- "Explain business meaning in plain language."
- "Offer at least two next actions."
- "Emit an experiment plan approval gate."

### 4.2 AgentLoop

Runs one or more steps until the goal is complete or budget is exhausted.

```python
class AgentLoop:
    async def run(self, turn: TurnContext, decision: TurnDecision, goal: TurnGoal) -> TurnOutcome:
        observations = []
        for step in range(goal.budgets.max_steps):
            action = await self.planner.next_action(turn, decision, goal, observations)
            result = await self.executor.execute(turn, decision, goal, action)
            observations.append(result)
            if await self.critic.is_complete(turn, goal, observations):
                return await self.presenter.finish(turn, goal, observations)
        return await self.presenter.finish_partial(turn, goal, observations)
```

Budgets should be dynamic, not a single small constant. A shallow answer should
finish quickly, but difficult data reasoning must be allowed to run for many
steps when the user asks for depth or when the artifact quality is not yet good
enough.

Budget profiles:

```text
interactive_quick
  max_steps: 4-6
  max_llm_calls: 2-3
  max_phase_runs: 1
  max_repairs: 0-1
  max_seconds: 45-60

standard_analysis
  max_steps: 10-15
  max_llm_calls: 5-8
  max_phase_runs: 2
  max_repairs: 2
  max_seconds: 120-180

deep_analysis
  max_steps: 25-40
  max_llm_calls: 12-20
  max_phase_runs: 3-5
  max_repairs: 4-8
  max_seconds: 300-600

background_research
  max_steps: 50+
  max_llm_calls: bounded by cost policy
  max_phase_runs: bounded by artifact/version policy
  max_repairs: bounded by diminishing-return policy
  max_seconds: async/background, not blocking the composer
```

The user-facing app should choose the budget profile from intent, requested
depth, and interaction mode:

- "quickly", "briefly", simple factual question -> `interactive_quick`
- normal analysis or planning request -> `standard_analysis`
- "deeply", "as much as possible", "think hard", high-stakes planning ->
  `deep_analysis`
- long-running research, repeated backtesting, or broad exploration ->
  `background_research`

For hard analysis, a 3-4 step loop is too short. The loop should be able to run
dozens of internal actions when the goal justifies it, while still emitting
progress and allowing cancellation.

### 4.3 Planner

Chooses the next action from a bounded action vocabulary.

Allowed actions:

```text
RUN_ANALYSIS
RUN_HYPOTHESIS
RUN_PLAN
EXPLAIN_ARTIFACTS
ANSWER_WITH_CONTEXT
REPAIR_LAST_ARTIFACT
ASK_CLARIFYING_QUESTION
STOP
```

The planner can be LLM-assisted, but the executor validates every action against
the current state and reducer decision.

### 4.4 ActionExecutor

Maps loop actions to existing behavior:

- `RUN_ANALYSIS` -> `AnalysisRoundRunner`
- `RUN_HYPOTHESIS` -> `HypothesisRoundRunner`
- `RUN_PLAN` -> `PlanRoundRunner`
- `EXPLAIN_ARTIFACTS` / `ANSWER_WITH_CONTEXT` -> new `ConversationAdvisor`
- `REPAIR_LAST_ARTIFACT` -> future repair runner
- `ASK_CLARIFYING_QUESTION` -> existing clarify emitter

### 4.5 ConversationAdvisor

A user-facing LLM worker dedicated to explanation, synthesis, and next-step
guidance. This should replace direct use of `decision.delta.reply` for most
non-trivial direct replies.

The advisor receives:

- full conversation transcript
- full phase artifacts JSON
- live block timeline
- reducer decision
- turn goal and completion criteria

It should not create workflow state. It creates explanatory text only.

Prompt principles:

- Match the depth requested by the user.
- Use the user's language when responding conversationally.
- Reference concrete artifact names/ids where helpful.
- Do not invent metrics, evidence, or approvals.
- When the next workflow action is obvious, recommend it.

### 4.6 Critic

Checks whether the observations satisfy the goal.

Start deterministic where possible:

- If goal requires `RUN_PLAN`, require an experiment plan artifact and approval block.
- If goal requires "explain every signal", check that every signal title or id appears.
- If goal requires next actions, check that the response includes action options.

Use an LLM critic only for semantic completeness when deterministic checks are
insufficient.

## 5. How This Changes Existing Flow

### 5.1 Direct Chat

Current:

```text
DIRECT -> use artifact lookup or interpreter reply -> stop
```

Proposed:

```text
DIRECT -> GoalController(answer/explain) -> AgentLoop -> ConversationAdvisor -> Critic -> stop
```

This fixes shallow one-shot replies without letting the interpreter become a
general responder.

### 5.2 Phase Execution

Current:

```text
RERUN -> run current phase once -> stop
```

Proposed:

```text
RERUN -> GoalController(run phase) -> AgentLoop
  -> run phase
  -> validate/observe emitted artifact
  -> optionally repair once
  -> advisor narration
  -> stop
```

### 5.3 Planning From Hypothesis Selection

Current failure mode:

```text
User: "2번 가설을 택할게"
Agent: acknowledges selection
User: "응 그러자"
Agent: may treat this as approval/direct reply without drafting plan
```

Proposed behavior:

```text
GoalController resolves a planning goal from the full transcript and artifacts.
AgentLoop runs RUN_PLAN.
Critic requires an experiment_plan artifact plus approval block before stopping.
```

No special hardcoded Korean phrase is required. The loop completion criteria
make the correct behavior natural and auditable.

## 6. Implementation Phases

### Phase 1: Advisor Split

Goal: stop shallow direct replies.

- Add `ConversationAdvisor` worker.
- Remove or ignore `reply` from `TurnInterpreter` except for clarifications.
- Change `TurnRouter._direct` to call advisor with full context.
- Remove "briefly" and "few sentences" from the chat prompt. Replace with
  "match the user's requested depth".

Verification:

- Asking "explain the analysis in detail" yields a multi-section answer covering
  all signal artifacts.
- Asking a small question still yields a concise answer.

### Phase 2: GoalController

Goal: turn each user request into explicit completion criteria.

- Add `TurnGoal` model.
- Map reducer decisions to goal kinds.
- Include selected artifact ids, target phase, depth, and completion criteria.
- Log/stream a short "goal selected" activity for observability.

Verification:

- "2번 가설로 계획 세워줘" produces a goal with `kind=run_phase`,
  `target_phase=EXPERIMENT_PLAN`, and selected hypothesis evidence.
- "설명해" after analysis produces `kind=explain_artifacts`.

### Phase 3: AgentLoop Skeleton

Goal: enable multi-step execution under budget.

- Add `AgentLoop`, `LoopAction`, `LoopObservation`, and `LoopBudget`.
- Add budget profiles, not one hardcoded max step count.
- Initially support:
  - `RUN_PHASE`
  - `ANSWER_WITH_CONTEXT`
  - `STOP`
- Use `interactive_quick` for ordinary chat and `standard_analysis` for normal
  workflow turns.

Verification:

- Phase request still emits the same artifacts as before.
- Direct answer routes through advisor.
- Loop emits progress events that distinguish real loop steps from plumbing.

### Phase 4: Critic and Repair

Goal: stop only when the goal is actually satisfied.

- Add deterministic critic checks for expected artifacts and approval gates.
- Add one repair retry for schema/validation failures where safe.
- Keep reviewer gate authoritative.
- Allow `deep_analysis` to perform many more observe/critique/repair iterations
  when the user explicitly asks for depth.

Verification:

- If planning is requested, the loop cannot stop with only a conversational
  acknowledgement.
- If an experiment plan fails validation, it retries once or emits a clear error.

### Phase 5: UX Alignment

Goal: make autonomy visible without noise.

- Rename low-value plumbing events or group them separately.
- Show meaningful loop steps:
  - "Goal selected"
  - "Drafting plan"
  - "Checking completeness"
  - "Explaining result"
- Keep raw chain-of-thought hidden.

### Phase 6: Long-Running Background Loops

Goal: support truly long work without blocking the chat composer.

- Add background loop records with run id, status, current step, and cancellation.
- Stream progress continuously over the existing thread timeline.
- Let the user keep chatting while a deep/background run continues.
- Save intermediate observations and artifact versions so a long run can resume
  after reconnect or container restart.

Verification:

- A `background_research` goal can run dozens of steps without freezing the UI.
- The user can cancel the run.
- Reconnect replays progress and final artifacts.

## 7. Risks and Guardrails

### Latency

Looping can make the app slower. Mitigation:

- Dynamic budget profiles instead of one global small budget.
- Visible progress events and cancellation for long loops.
- Background mode for long-running research loops.
- Stop after deterministic completeness when possible.
- Avoid running extra LLM critic for simple checks.

### Cost

Advisor and critic add calls. Mitigation:

- Direct shallow requests use one advisor call.
- Critic starts deterministic.
- Phase workers remain the expensive path and are limited per turn.

### Nondeterministic Control

More autonomy can make workflow less predictable. Mitigation:

- Bounded action vocabulary.
- Deterministic action eligibility.
- Reducer remains authoritative.
- Approval persistence remains Java-owned.

### Prompt Bloat

Full transcript and artifacts improve continuity but may grow. The current user
preference is to pass the full session while context allows. If this becomes
unstable, introduce model-native context caching or summarization only after the
full-context behavior is proven too slow or too large.

## 8. Immediate Next Change

The next code change should be Phase 1:

1. Add a `ConversationAdvisor` worker.
2. Change direct replies to use the advisor.
3. Remove short-answer bias from `CHAT`.
4. Keep `TurnInterpreter` as classifier/proposer only.

This is the smallest change that moves the product from "dispatcher that replies"
toward "agent that explains, guides, and adapts work depth".
