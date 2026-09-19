#!/usr/bin/env python3
"""
Standalone Home Assistant Model Context Protocol (MCP) Diagnostic Probe.
Tests initialization, tool discovery, and live context retrieval.
"""

import argparse
import json
import sys
import urllib.request
import urllib.error

def rpc(url, token, payload):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8")) if e.headers.get("content-type") == "application/json" else {"error": e.read().decode("utf-8")}
    except Exception as e:
        return 0, {"error": str(e)}

def main():
    parser = argparse.ArgumentParser(description="Test Home Assistant MCP Server")
    parser.add_argument("--url", required=True, help="MCP endpoint, e.g. http://192.168.1.100:8123/api/mcp")
    parser.add_argument("--token", required=True, help="Home Assistant Long-Lived Access Token")
    args = parser.parse_args()

    print(f"Connecting to {args.url}...")
    
    # 1. Initialize
    status, res = rpc(args.url, args.token, {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"}
        }
    })
    if status != 200:
        print(f"[FAIL] Initialize returned status {status}: {res}")
        sys.exit(1)
    server_info = res.get("result", {}).get("serverInfo", {})
    print(f"[OK] Initialized with server: {server_info.get('name')} v{server_info.get('version')}")

    # 2. Tools List
    status, res = rpc(args.url, args.token, {
        "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}
    })
    tools = res.get("result", {}).get("tools", [])
    print(f"[OK] Discovered {len(tools)} tools:")
    for t in tools:
        print(f"  - {t['name']}: {t.get('description', '')[:70]}...")

    # 3. Live Context Snapshot
    status, res = rpc(args.url, args.token, {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "homeassistant__GetLiveContext", "arguments": {}}
    })
    if status == 200 and "result" in res:
        print("\n[OK] Live Context Snapshot retrieved successfully!")
        print(res["result"])
    else:
        print(f"\n[FAIL] GetLiveContext failed: {res}")

if __name__ == "__main__":
    main()
