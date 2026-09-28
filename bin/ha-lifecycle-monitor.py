#!/usr/bin/env python3
"""
Home Assistant Real-Time Lifecycle Monitor & Telegram Notifier
Continuously watches Home Assistant core state and MCP server responsiveness,
detects restarts, shutdowns, and recoveries, proactively notifies the user via
Telegram with real-time status updates, and records lifecycle state for the agent.
"""
import json
import logging
import os
import sys
import time
import urllib.request
import urllib.error
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ha-lifecycle-monitor")

STATE_FILE = os.getenv("HA_STATE_FILE", "/opt/fleet/agents/ha-agent/runtime/ha_lifecycle_state.json")
MEMORY_FILE = os.getenv("HA_MEMORY_FILE", "/opt/fleet/agents/ha-agent/memories/MEMORY.md")
DEFAULT_HA_URL = "http://192.168.50.106:8123"

def load_secrets():
    """
    Dynamically loads secrets and configuration.
    Priority:
      1. /opt/fleet/etc/ha-monitor.env (Dedicated monitor config)
      2. /opt/fleet/agents/ha-agent/.env (Agent config)
      3. Process environment variables
      4. /opt/fleet/secrets.env (Fleet fallback)
    """
    ha_url = os.getenv("HA_URL")
    poll_interval = int(os.getenv("HA_POLL_INTERVAL", "5"))
    token = os.getenv("MCP_HOMEASSISTANT_API_KEY") or os.getenv("HA_LONG_LIVED_ACCESS_TOKEN")
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_users = [u.strip() for u in os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",") if u.strip()]

    env_paths = [
        "/opt/fleet/etc/ha-monitor.env",
        "/opt/fleet/agents/ha-agent/.env",
        "/opt/fleet/secrets.env"
    ]
    for p in env_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if "=" in line and not line.startswith("#"):
                            k, v = line.split("=", 1)
                            val = v.strip().strip('"\'')
                            if k == "HA_URL" and not ha_url:
                                ha_url = val
                            elif k == "HA_POLL_INTERVAL" and poll_interval == 5:
                                try:
                                    poll_interval = int(val)
                                except ValueError:
                                    pass
                            elif k in ("MCP_HOMEASSISTANT_API_KEY", "HA_LONG_LIVED_ACCESS_TOKEN") and not token:
                                token = val
                            elif k == "TELEGRAM_BOT_TOKEN" and not tg_token:
                                tg_token = val
                            elif k == "TELEGRAM_ALLOWED_USERS" and not tg_users:
                                tg_users = [u.strip() for u in val.split(",") if u.strip()]
            except Exception as e:
                logger.debug(f"Error reading {p}: {e}")

    ha_url = ha_url or DEFAULT_HA_URL
    return ha_url, poll_interval, token, tg_token, tg_users

def send_telegram_alert(tg_token: str, chat_ids: list, message: str, max_retries: int = 3):
    """
    Dispatches a Telegram message to configured chat IDs with automatic retries.
    """
    if not tg_token or not chat_ids:
        logger.warning("Cannot send alert: Missing Telegram token or chat IDs")
        return False
    url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
    success = True
    for cid in chat_ids:
        sent = False
        for attempt in range(1, max_retries + 1):
            try:
                r = requests.post(url, json={
                    "chat_id": cid,
                    "text": message,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True
                }, timeout=10)
                res = r.json()
                if res.get("ok"):
                    logger.info(f"Alert successfully sent to chat {cid} (attempt {attempt})")
                    sent = True
                    break
                else:
                    logger.warning(f"Telegram error (attempt {attempt}/{max_retries}): {res.get('description', r.text)}")
            except Exception as e:
                logger.warning(f"Telegram connection exception (attempt {attempt}/{max_retries}): {e}")
            time.sleep(1.5 * attempt)
        if not sent:
            logger.error(f"Failed to deliver alert to chat {cid} after {max_retries} attempts.")
            success = False
    return success

def probe_ha(ha_url: str, ha_token: str):
    """
    Probes both Home Assistant core API and MCP endpoint.
    """
    headers = {"Authorization": f"Bearer {ha_token}"} if ha_token else {}
    req = urllib.request.Request(f"{ha_url}/api/config", headers=headers)
    mcp_req = urllib.request.Request(f"{ha_url}/api/mcp", headers=headers)

    res = {
        "healthy": False,
        "state": "UNKNOWN",
        "version": "unknown",
        "mcp_active": False,
        "error": None
    }

    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                res["healthy"] = True
                res["state"] = data.get("state", "RUNNING")
                res["version"] = data.get("version", "unknown")
            else:
                res["error"] = f"HTTP status {resp.status}"
    except urllib.error.HTTPError as e:
        res["error"] = f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        res["error"] = str(e)

    # If core responded, probe MCP endpoint
    if res["healthy"]:
        try:
            with urllib.request.urlopen(mcp_req, timeout=3) as mcp_resp:
                res["mcp_active"] = (mcp_resp.status in (200, 405))
        except urllib.error.HTTPError as e:
            # 405 Method Not Allowed indicates MCP endpoint is active (requires POST)
            res["mcp_active"] = (e.code in (200, 405))
        except Exception:
            res["mcp_active"] = False

    return res

def persist_agent_state(current_state: str, ha_url: str, ha_version: str, mcp_active: bool,
                        transition_str: str, downtime_secs: int, last_msg: str, chat_ids: list):
    """
    Persists structured state to runtime JSON and memory for the ha-agent container.
    """
    state_payload = {
        "current_state": current_state,
        "ha_url": ha_url,
        "ha_version": ha_version,
        "mcp_active": mcp_active,
        "last_transition": transition_str,
        "downtime_duration_seconds": downtime_secs,
        "last_alert_sent": last_msg,
        "notified_chat_ids": chat_ids,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

    # Write runtime state file
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        tmp_file = f"{STATE_FILE}.tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(state_payload, f, indent=2)
        os.replace(tmp_file, STATE_FILE)
        try:
            os.chown(STATE_FILE, 10000, 10000)
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"Could not persist agent state file: {e}")

    # Synchronize agent MEMORY.md if accessible
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                content = f.read()

            marker = "Magnolia HA lifecycle status:"
            new_entry = f"{marker} As of {transition_str}, Home Assistant is {current_state} (v{ha_version}, MCP {'operational' if mcp_active else 'inactive'}). Real-time watcher actively alerts user."
            
            sections = [s.strip() for s in content.split("§") if s.strip()]
            filtered_sections = [s for s in sections if not s.startswith(marker)]
            filtered_sections.append(new_entry)

            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                f.write("\n§\n".join(filtered_sections) + "\n")
            try:
                os.chown(MEMORY_FILE, 10000, 10000)
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"Could not update MEMORY.md: {e}")

def main():
    ha_url, poll_interval, ha_token, tg_token, tg_users = load_secrets()
    logger.info(f"Starting HA Lifecycle Monitor targeting {ha_url} (poll interval: {poll_interval}s)")
    if not tg_token:
        logger.error("No Telegram bot token found. Exiting.")
        sys.exit(1)

    current_state = "UNKNOWN"
    consecutive_failures = 0
    restart_start_time = None
    last_version = "unknown"
    last_mcp = False

    # Initial probe
    initial = probe_ha(ha_url, ha_token)
    now_str = time.strftime("%Y-%m-%d %H:%M:%S PDT")
    if initial.get("healthy") and initial.get("state") == "RUNNING":
        current_state = "ONLINE"
        last_version = initial.get("version", "unknown")
        last_mcp = initial.get("mcp_active", True)
        logger.info(f"Initial state: ONLINE (HA version: {last_version}, MCP: {last_mcp})")
        persist_agent_state(current_state, ha_url, last_version, last_mcp, now_str, 0, "Monitor initialized: ONLINE", tg_users)
    else:
        current_state = "OFFLINE"
        logger.warning(f"Initial state: OFFLINE ({initial})")
        persist_agent_state(current_state, ha_url, last_version, last_mcp, now_str, 0, f"Monitor initialized: OFFLINE ({initial.get('error')})", tg_users)

    while True:
        time.sleep(poll_interval)
        ha_url, poll_interval, ha_token, tg_token, tg_users = load_secrets()
        res = probe_ha(ha_url, ha_token)
        now_str = time.strftime("%Y-%m-%d %H:%M:%S PDT")

        if res.get("healthy"):
            consecutive_failures = 0
            ha_state = res.get("state", "RUNNING")
            version = res.get("version", last_version)
            mcp_active = res.get("mcp_active", True)
            last_version = version
            last_mcp = mcp_active

            if ha_state == "RUNNING":
                if current_state in ("OFFLINE", "RESTARTING"):
                    logger.info("Transition detected: -> ONLINE")
                    downtime_secs = int(time.time() - restart_start_time) if restart_start_time else 0
                    msg = (
                        "✅ *Home Assistant is Online!*\n\n"
                        f"• *Core State:* `RUNNING`\n"
                        f"• *Version:* `{version}`\n"
                        f"• *MCP Server:* `/api/mcp` active & operational\n"
                        + (f"• *Downtime Duration:* `{downtime_secs}s`\n" if downtime_secs > 0 else "")
                        + f"⏱️ _{now_str}_"
                    )
                    send_telegram_alert(tg_token, tg_users, msg)
                    current_state = "ONLINE"
                    restart_start_time = None
                    persist_agent_state(current_state, ha_url, version, mcp_active, now_str, 0, msg, tg_users)
                elif current_state == "UNKNOWN":
                    current_state = "ONLINE"
                    persist_agent_state(current_state, ha_url, version, mcp_active, now_str, 0, "State confirmed ONLINE", tg_users)

            elif ha_state in ("STOPPING", "STARTING"):
                if current_state != "RESTARTING":
                    logger.info(f"Transition detected: -> RESTARTING (reported state: {ha_state})")
                    msg = (
                        "🔄 *Home Assistant is Restarting...*\n\n"
                        f"Core reported state: `{ha_state}`.\n"
                        "Standing by to verify when core services and MCP endpoints resume.\n"
                        f"⏱️ _{now_str}_"
                    )
                    send_telegram_alert(tg_token, tg_users, msg)
                    current_state = "RESTARTING"
                    restart_start_time = time.time()
                    persist_agent_state(current_state, ha_url, version, False, now_str, 0, msg, tg_users)

        else:
            consecutive_failures += 1
            err_reason = res.get("error", "Unreachable")

            if current_state == "ONLINE":
                if consecutive_failures == 1:
                    logger.info(f"Connection dropped ({err_reason}). Watching next tick for restart or offline...")
                elif consecutive_failures >= 2:
                    logger.info("Transition detected: -> RESTARTING / DOWN")
                    msg = (
                        "🔄 *Home Assistant is Restarting or Offline*\n\n"
                        f"Connection dropped: `{err_reason}`.\n"
                        "Monitoring for core recovery...\n"
                        f"⏱️ _{now_str}_"
                    )
                    send_telegram_alert(tg_token, tg_users, msg)
                    current_state = "RESTARTING"
                    restart_start_time = time.time()
                    persist_agent_state(current_state, ha_url, last_version, False, now_str, 0, msg, tg_users)

            elif current_state == "RESTARTING":
                downtime_secs = int(time.time() - restart_start_time) if restart_start_time else 0
                if restart_start_time and downtime_secs > 60:
                    logger.warning("Restart window exceeded 60 seconds. Declaring OFFLINE.")
                    msg = (
                        "🛑 *Home Assistant has Shut Down / is Offline*\n\n"
                        f"The host at `{ha_url}` has been unreachable for `{downtime_secs}s`.\n"
                        f"• *Last Error:* `{err_reason}`\n"
                        "• *Recommended Action:* Check VirtualBox VM power status if shutdown was intended.\n"
                        f"⏱️ _{now_str}_"
                    )
                    send_telegram_alert(tg_token, tg_users, msg)
                    current_state = "OFFLINE"
                    persist_agent_state(current_state, ha_url, last_version, False, now_str, downtime_secs, msg, tg_users)

if __name__ == "__main__":
    main()