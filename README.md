# LaunchPilot

LaunchPilot is an AI agent workroom platform for content and growth teams.

This repository currently contains the architecture diagrams, component contracts, example payloads, and contract verification tooling for the hackathon MVP.

## Documentation

- [Architecture diagrams](docs/architecture/launchpilot-c4.md)
- [MVP Product Requirements & Traceability](docs/product/mvp-product-requirements.md)
- [Frontend Architecture Decision](docs/frontend/frontend-architecture-decision.md)
- [Frontend State Machine Specification](docs/frontend/frontend-state-machine.md)
- [Contract index](contracts/README.md)
- [Scenario contract tests](scenarios/README.md)
- [Playwright E2E acceptance tests](e2e/README.md)

## Contract Verification

Run all repository-level checks:

```sh
npm test
```

Run contract checks only:

```sh
npm run test:contracts
```

Run conversation-first scenario coverage checks only:

```sh
npm run test:scenarios
```

List Playwright E2E acceptance tests:

```sh
npm run test:e2e:list
```

Run real-stack Playwright E2E tests (starts frontend, backend, and agent
containers; requires real Gemini/Vertex and Elastic credentials):

```sh
E2E_ENV_FILE=s.env npm run test:e2e:real
```

Run generic Playwright tests against the configured stack:

```sh
npm run test:e2e
```

The real-stack Playwright spec is the executable source of truth for the
conversation-first full system flow.

The verifier checks JSON/YAML/NDJSON parsing, JSON Schema example conformance, cross-contract enum consistency, evidence reference grounding, Elastic document links, OpenInference trace links, and conversation-first E2E scenario coverage.
