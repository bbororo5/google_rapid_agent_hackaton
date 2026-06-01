# Scenario Contract Tests

Scenario contract tests describe end-to-end product flows before the implementation exists.

They do not start the frontend, Java backend, Python agent, Elastic, or Phoenix. Instead, they verify that the contract fixtures already describe a coherent executable scenario:

- request and response order,
- state transitions,
- ID propagation,
- approval persistence links,
- evidence grounding,
- OpenInference trace linkage.

This is the first stage of E2E testing.

```text
Phase 1: Scenario contract test
  Uses contract fixtures only.

Phase 2: Mock E2E
  Runs against mocks/stubs generated from the same contracts.

Phase 3: Real E2E
  Runs against frontend + Java + Python + test Elastic/Phoenix.
```

Run:

```sh
npm run test:scenarios
```

Run all repository gates:

```sh
npm test
```
