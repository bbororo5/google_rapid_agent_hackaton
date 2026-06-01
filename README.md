# LaunchPilot

LaunchPilot is an AI agent workroom platform for content and growth teams.

This repository currently contains the architecture diagrams, component contracts, example payloads, and contract verification tooling for the hackathon MVP.

## Documentation

- [Architecture diagrams](docs/architecture/launchpilot-c4.md)
- [Contract index](contracts/README.md)
- [Scenario contract tests](scenarios/README.md)

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

The verifier checks JSON/YAML/NDJSON parsing, JSON Schema example conformance, cross-contract enum consistency, evidence reference grounding, Elastic document links, and OpenInference trace links.
