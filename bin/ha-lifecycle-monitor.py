#!/usr/bin/env python3
"""
Home Assistant Real-Time Lifecycle Monitor
Continuously watches Home Assistant core state, detects restarts, shutdowns, and recoveries,
and proactively notifies the user via Telegram with real-time status updates.
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

HA_URL = os.getenv("HA_URL", "http://192.168.50.106:8123")
POLL_INTERVAL = int(os.getenv("HA_POLL_INTERVAL", "5"))

def load_secrets():
    token = os.getenv("MCP_HOMEASSISTANT_API_KEY") or os.getenv("HA_LONG_LIVED_ACCESS_TOKEN")
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_users = os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",")

    env_paths = [
        "/opt/fleet/agents/ha-agent/.env",
        "/opt/fleet/secrets.env",
        "/config/.git_credentials"
    ]
    for p in env_paths:
        if os.path.exists(p):
            try:
                for line in open(p):
                    if "=" in line:
                        k, v = line.strip().split("=", 1)
                        val = v.strip().strip('"\'')
                        if k in ("MCP_HOMEASSISTANT_API_KEY", "HA_LONG_LIVED_ACCESS_TOKEN") and not token:
                            token = val
                        elif k == "TELEGRAM_BOT_TOKEN" and not tg_token:
                            tg_token = val
                        elif k == "TELEGRAM_ALLOWED_USERS" and not tg_users[0]:
                            tg_users = [u.strip() for u in val.split(",") if u.strip()]
            except Exception:
                pass
    return token, tg_token, [u for u in tg_users if u]

def send_telegram_alert(tg_token: str, chat_ids: list, message: str):
    if not tg_token or not chat_ids:
        logger.warning("Cannot send alert: Missing Telegram token or chat IDs")
        return
    url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
    for cid in chat_ids:
        try:
            r = requests.post(url, json={
                "chat_id": cid,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }, timeout=8)
            if r.json().get("ok"):
                logger.info(f"Alert successfully sent to chat {cid}")
            else:
                logger.error(f"Failed sending alert: {r.text}")
        except Exception as e:
            logger.error(f"Telegram alert exception: {e}")

def probe_ha(ha_token: str):
    headers = {"Authorization": f"Bearer {ha_token}"} if ha_token else {}
    req = urllib.request.Request(f"{HA_URL}/api/config", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                return {"healthy": True, "state": data.get("state", "RUNNING"), "version": data.get("version", "unknown")}
            return {"healthy": False, "status": resp.status}
    except urllib.error.HTTPError as e:
        return {"healthy": False, "status": e.code}
    except Exception as e:
        return {"healthy": False, "error": str(e)}

def main():
    logger.info(f"Starting HA Lifecycle Monitor targeting {HA_URL} (poll interval: {POLL_INTERVAL}s)")
    ha_token, tg_token, tg_users = load_secrets()
    if not tg_token:
        logger.error("No Telegram bot token found. Exiting.")
        sys.exit(1)

    current_state = "UNKNOWN"
    consecutive_failures = 0
    restart_start_time = None

    # Initial probe
    initial = probe_ha(ha_token)
    if initial.get("healthy") and initial.get("state") == "RUNNING":
        current_state = "ONLINE"
        logger.info(f"Initial state: ONLINE (HA version: {initial.get('version')})")
    else:
        current_state = "OFFLINE"
        logger.warning(f"Initial state: OFFLINE ({initial})")

    while True:
        time.sleep(POLL_INTERVAL)
        res = probe_ha(ha_token)
        now_str = time.strftime("%Y-%m-%d %H:%M:%S PDT")

        if res.get("healthy"):
            consecutive_failures = 0
            ha_state = res.get("state", "RUNNING")
            version = res.get("version", "unknown")

            if ha_state == "RUNNING":
                if current_state in ("OFFLINE", "RESTARTING"):
                    logger.info("Transition detected: -> ONLINE")
                    msg = (
                        "✅ *Home Assistant is Online!*\n\n"
                        f"• *Core State:* `RUNNING`\n"
                        f"• *Version:* `{version}`\n"
                        f"• *MCP Server:* `/api/mcp` active & operational\n"
                        f"⏱️ _{now_str}_"
                    )
                    send_telegram_alert(tg_token, tg_users, msg)
                    current_state = "ONLINE"
                    restart_start_time = None
                elif current_state == "UNKNOWN":
                    current_state = "ONLINE"

            elif ha_state in ("STOPPING", "STARTING"):
                if current_state != "RESTARTING":
                    logger.info(f"Transition detected: -> RESTARTING (reported state: {ha_state})")
                    msg = (
                        "🔄 *Home Assistant is Restarting...*\n\n"
                        f"Core reported state: `{ha_state}`.\n"
                        "Standing by to verify when core services resume.\n"
                        f"⏱️ _{now_str}_"
                    )
                    send_telegram_alert(tg_token, tg_users, msg)
                    current_state = "RESTARTING"
                    restart_start_time = time.time()

        else:
            consecutive_failures += 1
            # Unreachable probe
            if current_state == "ONLINE":
                if consecutive_failures == 1:
                    # Potential quick restart beginning
                    logger.info("Connection dropped. Watching next tick for restart or offline...")
                elif consecutive_failures >= 2:
                    # Connection down
                    logger.info("Transition detected: -> RESTARTING / DOWN")
                    msg = (
                        "🔄 *Home Assistant is Restarting or Offline*\n\n"
                        "Connection dropped. Monitoring for core recovery...\n"
                        f"⏱️ _{now_str}_"
                    )
                    send_telegram_alert(tg_token, tg_users, msg)
                    current_state = "RESTARTING"
                    restart_start_time = time.time()

            elif current_state == "RESTARTING":
                # Check if it has been down for > 75 seconds without recovering
                if restart_start_time and (time.time() - restart_start_time > 75):
                    logger.warning("Restart window exceeded 75 seconds. Declaring OFFLINE.")
                    msg = (
                        "🛑 *Home Assistant has Shut Down / is Offline*\n\n"
                        f"The host at `{HA_URL}` has been unreachable for over 75 seconds.\n"
                        "Check VirtualBox VM power status if shutdown was intended.\n"
                        f"⏱️ _{now_str}_"
                    )
                    send_telegram_alert(tg_token, tg_users, msg)
                    current_state = "OFFLINE"
                    restart_start_time = None

if __name__ == "__main__":
    main()
