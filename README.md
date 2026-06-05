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

Run Playwright E2E tests:

```sh
npm run test:e2e
```

The scenario verifier now treats the Playwright E2E specs as the executable source of truth for conversation-first user flows.

The verifier checks JSON/YAML/NDJSON parsing, JSON Schema example conformance, cross-contract enum consistency, evidence reference grounding, Elastic document links, OpenInference trace links, and conversation-first E2E scenario coverage.
