#!/usr/bin/env bash
# Provision and launch the containerized ha-agent supervised by systemd.
set -euo pipefail

NAME="${1:-ha-agent}"
HA_URL="${2:-http://<homeassistant-ip>:8123/api/mcp}"
HA_TOKEN="${3:-}"

if [ -z "$HA_TOKEN" ]; then
  echo "Usage: $0 [name] <ha-url> <ha-long-lived-token>" >&2
  exit 1
fi

AGENT_DIR="/opt/fleet/agents/${NAME}"
mkdir -p "$AGENT_DIR"
chmod 750 "$AGENT_DIR"

cat <<EOF > "${AGENT_DIR}/.env"
MCP_HOMEASSISTANT_API_KEY=${HA_TOKEN}
EOF
chmod 600 "${AGENT_DIR}/.env"

cat <<EOF > "${AGENT_DIR}/config.yaml"
_config_version: 12
mcp_servers:
  homeassistant:
    url: "${HA_URL}"
    headers:
      Authorization: "Bearer \${MCP_HOMEASSISTANT_API_KEY}"
    enabled: true
EOF

echo "Configured ${NAME} in ${AGENT_DIR}."
