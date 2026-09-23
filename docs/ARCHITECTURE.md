# Architecture & Protocol Specification

## Communication Sequence

```mermaid
sequenceDiagram
    participant User
    participant Hermes as Hermes Agent (ha-agent)
    participant HA as Home Assistant (/api/mcp)
    participant Entities as Home Entities / Sensors

    User->>Hermes: "Check living room temperature"
    Note over Hermes: Context-First Rule
    Hermes->>HA: POST /api/mcp (tools/call: homeassistant__GetLiveContext)
    HA->>Entities: Read live states & attributes (Filtered by exposed_entities)
    Entities-->>HA: Current telemetry (Local site only)
    HA-->>Hermes: Live Context Snapshot JSON
    Note over Hermes: Reason over entities & values
    Hermes->>User: "Living room temperature is 68.9°F"
```

## Multi-Location Isolation & Entity Filtering Architecture

```mermaid
flowchart TD
    subgraph Cloud["Shared Cloud Accounts"]
        Tuya["Tuya Smart (50+ devices)"]
        Wyze["Wyze Plugs & Cams"]
        Ring["Ring Protect"]
    end

    subgraph Sites["Physical Sites"]
        SiteA["Site A: Local Physical Location"]
        SiteB["Site B: Remote Studios & Warehouses"]
    end

    Tuya --> SiteA & SiteB
    Wyze --> SiteA & SiteB
    Ring --> SiteA & SiteB

    subgraph HA["Home Assistant Instance"]
        Integrations["Integrations (Imports all cloud devices)"]
        Gatekeeper["Assist Exposure Gatekeeper (exposed_entities)"]
        MCPServer["MCP Server (/api/mcp)"]
    end

    Cloud --> Integrations
    Integrations --> Gatekeeper
    Gatekeeper -- "Passes local site entities ONLY" --> MCPServer
    Gatekeeper -- "Blocks remote/external entities" --> Blocked["Blocked from MCP & Assist"]

    MCPServer <--> |Streamable HTTP JSON-RPC| HermesAgent["Hermes ha-agent"]
```

## Protocol Details
- **Protocol**: Model Context Protocol (MCP) 2024-11-05 / 2025-06-18
- **Transport**: Streamable HTTP with JSON-RPC 2.0 payloads
- **Payload Headers**:
  - `Authorization: Bearer <TOKEN>`
  - `Content-Type: application/json`
  - `Accept: application/json`
