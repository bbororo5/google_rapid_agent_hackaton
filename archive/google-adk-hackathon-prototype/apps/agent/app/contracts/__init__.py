"""Contract-enforced Pydantic models.

These are a faithful translation of:
- contracts/02-java-python-agent/openapi.yaml  (REST run API)
- contracts/02-java-python-agent/asyncapi.yaml (workflow event stream)
- contracts/05-agent-output/agent-output.schema.json (worker outputs)

`extra="forbid"` mirrors `additionalProperties: false`. Patterns/enums mirror
the JSON Schema constraints so any drift fails fast at the boundary.
"""
from app.contracts.schemas import *  # noqa: F401,F403
