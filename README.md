# Hermes Home Assistant MCP Agent (`hermes-home-assistant-mcp`)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.12%2B%20%7C%202026.x-41BDF5?logo=home-assistant)](https://www.home-assistant.io)
[![Model Context Protocol](https://img.shields.io/badge/MCP-Streamable%20HTTP-orange)](https://modelcontextprotocol.io)
[![Hermes Agent](https://img.shields.io/badge/Hermes-Agent-purple)](https://github.com/nousresearch/hermes-agent)

Autonomous **Hermes Agent** integration with **Home Assistant** via the official [Model Context Protocol (MCP) Server](https://www.home-assistant.io/integrations/mcp_server/). 

Enables AI agents to query real-time sensor telemetry, audit device states, control lights/switches/media players, manage to-do lists, and run automations with complete context awareness.

---

## Architecture Overview

```
+-------------------------------------------------------------------------+
| Home Network                                                            |
|                                                                         |
|  +-----------------------------------+                                  |
|  | Home Assistant Core / OS          |                                  |
|  | - Official mcp_server integration |                                  |
|  | - Assist API endpoint: /api/mcp   |                                  |
|  +-----------------+-----------------+                                  |
|                    ^                                                    |
|                    | Streamable HTTP (SSE) JSON-RPC 2.0                 |
|                    | Bearer Token Authentication                        |
|                    v                                                    |
|  +-----------------+-----------------+                                  |
|  | Autonomous Hermes Agent (ha-agent)|                                  |
|  | - Supervised Podman / Docker unit |                                  |
|  | - Multi-tier LLM reasoning        |                                  |
|  | - Context-First skill execution   |                                  |
|  +-----------------------------------+                                  |
+-------------------------------------------------------------------------+
```

---

## Key Features

- **Native MCP Protocol**: Interfaces directly with Home Assistant's official `/api/mcp` endpoint over Streamable HTTP (SSE) with stateless JSON-RPC 2.0 requests.
- **Context-First Paradigm**: Employs a strict discovery-first methodology — querying `homeassistant__GetLiveContext` to inspect current areas, entities, and attributes before taking action.
- **20 Assist Tools Supported**:
  - **Context**: `homeassistant__GetLiveContext`, `llm__GetDateTime`
  - **Entity Control**: `intent__HassTurnOn`, `intent__HassTurnOff`, `intent__HassCancelAllTimers`
  - **Lighting**: `light__HassLightSet` (brightness, RGB/color)
  - **Media Playback**: `media_player__*` (play/pause, volume, skip, search & play)
  - **To-Do Management**: `todo__get_items`, `todo__HassListAddItem`, `todo__HassListCompleteItem`
  - **Broadcasting**: `assist_satellite__HassBroadcast`
- **Multi-Location Anti-Bleed Isolation**: Enforces physical site boundary guardrails. Prevents inadvertent actuation of remote location fixtures (e.g. secondary studios, remote smart plugs) across shared cloud integrations (Tuya, Wyze, Ring) via server-side Assist entity exposure filtering and agent-side location scoping.
- **Fleet Orchestration Ready**: Seamlessly attaches to the Hermes Fleet Controller or runs as a standalone supervised systemd service.
- **Strict Security & Token Isolation**: Tokens are isolated to local `.env` files and interpolated at runtime.

---

## Multi-Location Isolation & Device Scoping

In smart home deployments where single cloud vendor accounts (Tuya, Wyze, Ring, SmartThings) are shared across multiple physical properties or buildings (e.g. a main home, a separate studio, a warehouse), connecting those accounts to Home Assistant imports devices across **all** sites.

By default, Home Assistant exposes all discovered lights, switches, and media players to its Assist and MCP platforms. Without isolation, commands like `"turn on the lights"` or broad agent actions will actuate physical devices across different locations simultaneously.

### Two-Tier Anti-Bleed Architecture

1. **Server-Side Hardening (`exposed_entities`)**:
   - Only devices physically present at the local site are marked `should_expose: true` for the `conversation` assistant.
   - All external/cross-site devices are explicitly marked `should_expose: false`.
   - Automatic exposure of newly added devices is disabled (`expose_new: false`) so future cloud device additions never automatically leak into MCP knowledge.
   - When the agent initializes and queries `homeassistant__GetLiveContext`, Home Assistant's MCP server serializes *only* the local site's devices.

2. **Agent-Side Standing Invariants (`SOUL.md` & `SKILL.md`)**:
   - The agent is persona-bound to the specific physical site.
   - Broad commands must always resolve to local room groups (e.g., `Kitchen Lights`, `Bedroom Lights`, `All Presence Lights`).
   - The agent is forbidden from executing actions on entity IDs outside its verified local site roster.

---

## Quick Start Installation

### Step 1: Enable MCP Server in Home Assistant
1. In Home Assistant, navigate to **Settings > Devices & Services**.
2. Click **Add Integration** and select **Model Context Protocol Server**.
3. Select the **Assist** API and complete the configuration flow.
4. Generate a Long-Lived Access Token in your **User Profile > Security**.

### Step 2: Clone & Configure
```bash
git clone https://github.com/maximusmaximus/hermes-home-assistant-mcp.git
cd hermes-home-assistant-mcp

# Copy configuration templates
cp config/config.example.yaml config.yaml
cp config/secrets.env.example .env
```

Edit `.env` with your Home Assistant details:
```bash
HOMEASSISTANT_URL=http://<your-ha-ip>:8123/api/mcp
MCP_HOMEASSISTANT_API_KEY=your_long_lived_access_token_here
INFERENCE_API_KEY=your_llm_api_key_here
```

### Step 3: Test MCP Connection
Verify tool discovery using the included diagnostic script:
```bash
python3 bin/test-ha-mcp.py --url http://<your-ha-ip>:8123/api/mcp --token $MCP_HOMEASSISTANT_API_KEY
```

### Step 4: Run the Agent
Run directly with the Hermes CLI:
```bash
hermes chat -q "What is the status of the living room lights and sensors?"
```

Or deploy as a containerized systemd background service:
```bash
sudo ./bin/spawn-ha-agent.sh --name ha-agent --ha-url http://<your-ha-ip>:8123/api/mcp --ha-token $MCP_HOMEASSISTANT_API_KEY
```

---

## Repository Structure

```text
hermes-home-assistant-mcp/
├── bin/
│   ├── spawn-ha-agent.sh       # Automated agent provisioning script
│   └── test-ha-mcp.py          # Standalone MCP probe & diagnostic tool
├── config/
│   ├── config.example.yaml     # Hermes config template with mcp_servers
│   └── secrets.env.example     # Environment template for bearer credentials
├── docs/
│   ├── ARCHITECTURE.md         # Protocol specs and sequence diagrams
│   └── MCP_TOOLS.md            # Detailed tool reference and parameters
├── skills/
│   └── home-assistant-mcp/
│       └── SKILL.md            # Hermes Skill definition
├── souls/
│   └── ha-agent-soul.md        # Agent persona and standing orders
├── systemd/
│   └── hermes-ha-agent.service # Systemd unit template
├── LICENSE                     # MIT License
└── README.md
```

---

## Security Best Practices

1. **Local Network Isolation**: Keep the MCP endpoint restricted to your local LAN or secure mesh network (e.g. Tailscale / WireGuard).
2. **Exposed Entities Control**: In Home Assistant, visit the **Voice Assistants / Exposed Entities** settings to strictly limit which devices are visible to Assist.
3. **Never Hardcode Secrets**: Store all tokens in environment files mode `0600`.
