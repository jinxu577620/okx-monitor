"""推送工具：仅推送微信（直接发送，不走队列）"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

WX_CHANNEL = "openclaw-weixin"
MSG_DIR = Path(__file__).resolve().parent / "messages"
WX_TARGET = "o9cq806ek1SRbRvZEjLELF19jkVc@im.wechat"
WX_ACCOUNT_ID = "8928c3e5625b-im-bot"


def _caller_name() -> str:
    """推断调用脚本名"""
    # 从 sys.argv[0] 获取主脚本名
    try:
        name = Path(sys.argv[0]).name
        if name and name != "push_helper.py":
            return name.replace(".py", "")
    except Exception:
        pass
    return "unknown"


def _save_message(text: str) -> None:
    """缓存最近推送内容到文件"""
    try:
        MSG_DIR.mkdir(parents=True, exist_ok=True)
        name = _caller_name()
        record = {
            "script": name,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ts": time.time(),
            "length": len(text),
            "message": text,
        }
        (MSG_DIR / f"{name}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2), "utf-8"
        )
    except Exception:
        pass


def push_wechat(text: str) -> None:
    channel = os.getenv("OPENCLAW_PUSH_CHANNEL", WX_CHANNEL)
    target = os.getenv("OPENCLAW_PUSH_TARGET", WX_TARGET)
    account_id = os.getenv("OPENCLAW_PUSH_ACCOUNT_ID", WX_ACCOUNT_ID)

    cmd = [
        "openclaw", "message", "send",
        "--channel", channel,
        "--target", target,
        "--account", account_id,
        "--message", text,
    ]
    send_timeout = int(os.getenv("OPENCLAW_SEND_TIMEOUT", "120"))
    _save_message(text)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=send_timeout)
    if r.returncode != 0:
        raise RuntimeError(f"openclaw send failed: {(r.stderr or r.stdout).strip()}")


def push_all(text: str) -> None:
    """推送到微信"""
    try:
        push_wechat(text)
        print("  WECHAT_SENT")
    except Exception as e:
        print(f"  WECHAT_FAIL: {e}")
