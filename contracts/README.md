# LaunchPilot Contracts

This directory contains the contract set for LaunchPilot's hackathon MVP.

Architecture reference: [`docs/architecture/launchpilot-c4.md`](../docs/architecture/launchpilot-c4.md)

Read in order:

| Order | Boundary | Folder | Main Artifact |
| --- | --- | --- | --- |
| 1 | Frontend <-> Java Backend | `01-frontend-java` | `openapi.yaml` |
| 2 | Java Backend <-> Python Agent | `02-java-python-agent` | `openapi.yaml` |
| 3 | Java Backend <-> Elastic | `03-java-elastic` | `documents.schema.json` |
| 4 | Python Agent <-> Elasticsearch MCP | `04-agent-elastic-mcp` | `evidence-tools.schema.json` |
| 5 | ADK Workers <-> Structured Outputs | `05-agent-output` | `agent-output.schema.json` |
| 6 | Python Agent <-> Phoenix/Arize | `06-observability` | `openinference-traces.schema.json` |

## Directory Map

```text
contracts/
  01-frontend-java/
    README.md
    openapi.yaml
    frontend-types.ts
    examples/

  02-java-python-agent/
    README.md
    openapi.yaml
    examples/

  03-java-elastic/
    README.md
    documents.schema.json
    examples/

  04-agent-elastic-mcp/
    README.md
    evidence-tools.schema.json
    examples/

  05-agent-output/
    README.md
    agent-output.schema.json
    examples/

  06-observability/
    README.md
    openinference-traces.schema.json
    examples/
```

## Implementation Notes

- The frontend should start with `01-frontend-java/openapi.yaml` and `01-frontend-java/frontend-types.ts`.
- Java should implement public controllers from `01-frontend-java`, internal agent calls from `02-java-python-agent`, and Elastic writes from `03-java-elastic`.
- Python should implement internal agent API from `02-java-python-agent`, evidence wrappers from `04-agent-elastic-mcp`, structured worker output from `05-agent-output`, and OpenInference tracing from `06-observability`.
- The canonical final agent payload is `AgentResultPayload` from `01-frontend-java/openapi.yaml`.
- `tool_call_logs` are UI summaries. OpenInference spans in `06-observability` are the source of truth for trace-level observability.

## Verification

At minimum, all JSON and YAML files should parse:

```sh
ruby -e 'require "json"; require "yaml"; Dir["contracts/**/*.json"].each { |f| JSON.parse(File.read(f)) }; Dir["contracts/**/*.yaml"].each { |f| YAML.load_file(f) }; puts "ok"'
```
