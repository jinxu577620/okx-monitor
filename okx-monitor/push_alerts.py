from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

import requests

from check_alerts import main as collect_alerts_main
from io import StringIO
import contextlib

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "alert_push_state.json"
DEFAULT_TIMEOUT = 20


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(data: dict) -> None:
    STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def collect_alert_text() -> str:
    buf = StringIO()
    with contextlib.redirect_stdout(buf):
        collect_alerts_main()
    return buf.getvalue().strip()


def send_telegram(text: str) -> None:
    bot_token = os.getenv("TG_BOT_TOKEN")
    chat_id = os.getenv("TG_CHAT_ID")
    if not bot_token or not chat_id:
        raise RuntimeError("Missing TG_BOT_TOKEN or TG_CHAT_ID")

    timeout = int(os.getenv("REQUEST_TIMEOUT", str(DEFAULT_TIMEOUT)))
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    resp = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")


def main() -> None:
    alert_text = collect_alert_text()
    if not alert_text or alert_text == "NO_ALERTS":
        print("NO_ALERTS")
        return

    message = f"加密关键信号提醒\n更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n{alert_text}"
    content_hash = hashlib.sha256(message.encode("utf-8")).hexdigest()
    state = load_state()

    if state.get("last_hash") == content_hash:
        print("SKIPPED_DUPLICATE")
        return

    send_telegram(message)
    state["last_hash"] = content_hash
    state["last_sent_at"] = datetime.now().isoformat()
    save_state(state)
    print("PUSHED")


if __name__ == "__main__":
    main()
