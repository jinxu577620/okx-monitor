"""
每日暴涨回顾 — 每天 23:30 推送
回顾今日所有推送过的暴涨币：当时价格 vs 现价
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from push_helper import push_all

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

DINGTALK_WEBHOOK = os.getenv("DINGTALK_WEBHOOK", "")

STATE_FILE = BASE_DIR / "surge_state.json"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def send_dingtalk(text: str) -> bool:
    if not DINGTALK_WEBHOOK:
        return False
    payload = json.dumps({"msgtype": "text", "text": {"content": "加密 | " + text}}).encode("utf-8")
    req = Request(DINGTALK_WEBHOOK, data=payload, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read()).get("errcode") == 0
    except Exception:
        return False


def sf(v, d=0.0):
    try: return float(v)
    except: return d


def api_get(path, params=None, timeout=30):
    from okx_retry import okx_get_json
    url = f"https://www.okx.com{path}"
    return okx_get_json(url, params=params, headers=HEADERS, timeout=timeout, max_retries=3, backoff_base=2.0)


def load_state():
    if STATE_FILE.exists():
        try: return json.loads(STATE_FILE.read_text("utf-8"))
        except: pass
    return {"seen_coins": {}}


def price_str(price):
    if price >= 100:
        return f"${price:.2f}"
    elif price >= 1:
        return f"${price:.4f}"
    elif price >= 0.001:
        return f"${price:.6f}"
    else:
        return f"${price:.8f}"


def build_daily_report():
    t0 = time.time()
    state = load_state()
    seen = state.get("seen_coins", {})
    
    now = datetime.now(timezone.utc).astimezone()
    today_str = now.strftime("%Y-%m-%d")
    
    if not seen:
        msg = f"📋 今日暴涨回顾\n{now.strftime('%H:%M')} {today_str}\n\n今日无暴涨币记录"
        push_all(msg)
        if DINGTALK_WEBHOOK:
            send_dingtalk(msg)
        return
    
    # 拉取最新价格
    for name, info in seen.items():
        inst_id = f"{name}-USDT-SWAP"
        try:
            ticker = api_get("/api/v5/market/ticker", {"instId": inst_id}, timeout=10)
            row = ticker["data"][0]
            info["current_price"] = sf(row.get("last"))
        except:
            info["current_price"] = 0
    
    parts = [
        f"📋 今日暴涨回顾",
        f"{now.strftime('%H:%M')} {today_str}",
        f"共追踪 {len(seen)} 个币",
        "",
    ]
    
    # 按推送时涨幅排序
    sorted_coins = sorted(seen.items(), key=lambda x: abs(x[1].get("first_chg", 0)), reverse=True)
    
    for name, info in sorted_coins[:20]:
        push_price = info.get("first_price", 0)
        cur_price = info.get("current_price", 0)
        
        if push_price > 0 and cur_price > 0:
            pnl = (cur_price - push_price) / push_price * 100
            pnl_str = f"{'+' if pnl >= 0 else ''}{pnl:.1f}%"
        else:
            pnl_str = "--"
        
        parts.append(f"{name}  推送{price_str(push_price)} → 现{price_str(cur_price)}  盈亏{pnl_str}")
    
    msg = "\n".join(parts)
    push_all(msg)
    if DINGTALK_WEBHOOK:
        send_dingtalk(msg)
    print(f"DAILY_REPORT_PUSHED ({time.time()-t0:.1f}s)")


if __name__ == "__main__":
    build_daily_report()
