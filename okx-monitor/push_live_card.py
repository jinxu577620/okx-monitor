from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path

import requests

from live_card import build_live_card

BASE_DIR = Path(__file__).resolve().parent
PUSH_STATE_FILE = BASE_DIR / "push_state.json"
DEFAULT_TIMEOUT = 20


def load_push_state() -> dict:
    if not PUSH_STATE_FILE.exists():
        return {}
    try:
        import json

        return json.loads(PUSH_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_push_state(data: dict) -> None:
    import json

    PUSH_STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def render_message() -> str:
    title = os.getenv("CRYPTO_LIVE_TITLE", "加密监控推送")
    card = build_live_card()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"{title}\n更新时间：{now}\n\n{card}"


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
    message = render_message()
    content_hash = hashlib.sha256(message.encode("utf-8")).hexdigest()
    state = load_push_state()

    if os.getenv("SKIP_DUPLICATE_PUSH", "0") == "1" and state.get("last_hash") == content_hash:
        print("SKIPPED_DUPLICATE")
        return

    send_telegram(message)
    state["last_hash"] = content_hash
    state["last_sent_at"] = datetime.now().isoformat()
    save_push_state(state)
    print("PUSHED")


if __name__ == "__main__":
    main()
