# LaunchPilot

LaunchPilot is an AI agent workroom platform for content and growth teams.

This repository currently contains the architecture diagrams, component contracts, example payloads, and contract verification tooling for the hackathon MVP.

## Documentation

- [Architecture diagrams](docs/architecture/launchpilot-c4.md)
- [MVP requirements traceability](docs/product/mvp-requirements-traceability.md)
- [Frontend state machine](docs/frontend/state-machine.md)
- [Frontend screen architecture](docs/frontend/screen-architecture.md)
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

Run executable scenario contract checks only:

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

The Playwright E2E suite is intentionally allowed to be red before a frontend app is scaffolded. Its first happy-path spec is the acceptance target for the frontend implementation.

The verifier checks JSON/YAML/NDJSON parsing, JSON Schema example conformance, cross-contract enum consistency, evidence reference grounding, Elastic document links, and OpenInference trace links.
