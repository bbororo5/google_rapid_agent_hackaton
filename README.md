# LaunchPilot

LaunchPilot is an AI agent workroom platform for content and growth teams.

This repository currently contains the architecture diagrams, component contracts, example payloads, and contract verification tooling for the hackathon MVP.

## Documentation

- [Architecture diagrams](docs/architecture/launchpilot-c4.md)
- [Contract index](contracts/README.md)

## Contract Verification

Run the repository-level contract checks:

```sh
npm run test:contracts
```

The verifier checks JSON/YAML/NDJSON parsing, JSON Schema example conformance, cross-contract enum consistency, evidence reference grounding, Elastic document links, and OpenInference trace links.
