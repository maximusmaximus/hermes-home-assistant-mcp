#!/usr/bin/env python3
"""
Home Assistant System Action Utility
Executes authenticated Home Assistant system actions (Core restart, Host reboot/shutdown,
YAML reload, Agent restart, System health check) via HA REST API and local systemd.
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error
import subprocess

DEFAULT_HA_URL = os.getenv("HA_URL", "http://192.168.50.106:8123")

def load_ha_token():
    token = os.getenv("MCP_HOMEASSISTANT_API_KEY") or os.getenv("HA_LONG_LIVED_ACCESS_TOKEN")
    if token:
        return token.strip('"\'')
    # Try reading from ha-agent .env
    for env_path in [
        "/opt/fleet/agents/ha-agent/.env",
        "/opt/fleet/secrets.env",
        "/config/.git_credentials"
    ]:
        if os.path.exists(env_path):
            try:
                for line in open(env_path):
                    if line.startswith("MCP_HOMEASSISTANT_API_KEY=") or line.startswith("HA_LONG_LIVED_ACCESS_TOKEN="):
                        return line.split("=", 1)[1].strip().strip('"\'')
            except Exception:
                pass
    return None

def call_ha_service(endpoint: str, domain: str, service: str, data: dict = None):
    token = load_ha_token()
    if not token:
        return {"ok": False, "error": "Missing Home Assistant Long-Lived Access Token"}

    url = f"{endpoint}/api/services/{domain}/{service}"
    body = json.dumps(data or {}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {"ok": True, "status": resp.status, "response": resp.read().decode("utf-8")}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "error": e.read().decode("utf-8")}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def get_ha_status(endpoint: str):
    token = load_ha_token()
    result = {
        "ha_url": endpoint,
        "rest_api": "unknown",
        "mcp_server": "unknown",
        "core_state": "unknown",
        "core_version": "unknown",
        "ha_agent_service": "unknown"
    }
    
    # 1. Check REST API /api/config
    if token:
        try:
            req = urllib.request.Request(f"{endpoint}/api/config", headers={"Authorization": f"Bearer {token}"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode())
                result["rest_api"] = "ok"
                result["core_state"] = data.get("state", "UNKNOWN")
                result["core_version"] = data.get("version", "UNKNOWN")
        except Exception as e:
            result["rest_api"] = f"error: {e}"

    # 2. Check MCP Server /api/mcp
    if token:
        try:
            mcp_body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode()
            req = urllib.request.Request(f"{endpoint}/api/mcp", data=mcp_body, headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            })
            with urllib.request.urlopen(req, timeout=4) as resp:
                result["mcp_server"] = f"ok ({resp.status})"
        except Exception as e:
            result["mcp_server"] = f"error: {e}"

    # 3. Check hermes-ha-agent.service
    try:
        r = subprocess.run(["systemctl", "is-active", "hermes-ha-agent.service"], capture_output=True, text=True)
        result["ha_agent_service"] = r.stdout.strip() or "inactive"
    except Exception:
        result["ha_agent_service"] = "not_available"

    return result

def main():
    parser = argparse.ArgumentParser(description="Home Assistant System Action Dispatcher")
    parser.add_argument("action", choices=[
        "restart-ha", "reboot-host", "shutdown-host", "reload-yaml", "restart-agent", "status"
    ], help="System action to execute")
    parser.add_argument("--url", default=DEFAULT_HA_URL, help="Home Assistant base URL")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    if args.action == "status":
        st = get_ha_status(args.url)
        if args.json:
            print(json.dumps(st, indent=2))
        else:
            print("🏥 Home Assistant & Agent Status:")
            print(f"  • REST API:     {st['rest_api']}")
            print(f"  • Core State:   {st['core_state']}")
            print(f"  • Core Version: {st['core_version']}")
            print(f"  • MCP Server:   {st['mcp_server']}")
            print(f"  • Agent Daemon: {st['ha_agent_service']}")
        return

    if args.action == "restart-ha":
        print("[*] Requesting Home Assistant Core restart...")
        res = call_ha_service(args.url, "homeassistant", "restart")
        print("Success" if res.get("ok") else f"Failed: {res.get('error')}")

    elif args.action == "reboot-host":
        print("[*] Requesting Home Assistant Host reboot...")
        res = call_ha_service(args.url, "hassio", "host_reboot")
        print("Success" if res.get("ok") else f"Failed: {res.get('error')}")

    elif args.action == "shutdown-host":
        print("[*] Requesting Home Assistant Host shutdown...")
        res = call_ha_service(args.url, "hassio", "host_shutdown")
        print("Success" if res.get("ok") else f"Failed: {res.get('error')}")

    elif args.action == "reload-yaml":
        print("[*] Requesting Home Assistant reload all configurations...")
        res = call_ha_service(args.url, "homeassistant", "reload_all")
        print("Success" if res.get("ok") else f"Failed: {res.get('error')}")

    elif args.action == "restart-agent":
        print("[*] Restarting hermes-ha-agent.service...")
        try:
            subprocess.run(["systemctl", "restart", "hermes-ha-agent.service"], check=True)
            print("Success: hermes-ha-agent restarted.")
        except Exception as e:
            print(f"Failed to restart agent: {e}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
