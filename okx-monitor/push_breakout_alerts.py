from __future__ import annotations

import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

from scan_breakout_alerts import render_signals, scan

BASE_DIR = Path(__file__).resolve().parent
HEADERS = {"User-Agent": "Mozilla/5.0"}
DINGTALK_WEBHOOK = os.getenv("DINGTALK_WEBHOOK", "")
TRACKING_STATE = BASE_DIR / "breakout_alerts_tracking.json"
TRACKING_TTL_H = 24  # 24小时后清理
TRACKING_CHG_THRESHOLD = 3.0  # 涨跌幅阈值 (%)
EARLY_BIRD_MIN_SCORE = 8  # 早鸟预警最低评分
EARLY_BIRD_MAX_CHG = 8.0  # 早鸟预警最大24h涨幅 (%)
BREAKOUT_MIN_CHG = 15.0  # 强势突破最小24h涨幅 (%)


# ====== 往期追踪状态管理 ======

def load_tracking_state() -> dict[str, dict]:
    if TRACKING_STATE.exists():
        try:
            return json.loads(TRACKING_STATE.read_text("utf-8")).get("coins", {})
        except Exception:
            pass
    return {}


def save_tracking_state(coins: dict[str, dict]) -> None:
    TRACKING_STATE.write_text(
        json.dumps({"coins": coins, "updated": time.time()}, ensure_ascii=False, indent=2),
        "utf-8",
    )


def cleanup_tracking_state(coins: dict[str, dict]) -> dict[str, dict]:
    """清除超过 TTL 的记录"""
    cutoff = time.time() - TRACKING_TTL_H * 3600
    return {k: v for k, v in coins.items() if v.get("push_time", 0) >= cutoff}


def collect_current_coins(accumulating, pre_breakouts, resurging, steady, watch_list, enriched) -> dict[str, dict]:
    """从扫描结果中收集所有币种信息"""
    coins = {}
    now = time.time()
    categories = [
        (accumulating, "蓄力中"),
        (pre_breakouts, "突破在即"),
        (resurging, "卷土重来"),
        (steady, "稳健上涨"),
        (watch_list, "观察清单"),
        (enriched[:2], "重点推荐"),
    ]
    for group, cat in categories:
        for row in group:
            inst_id = row.get("instId", "")
            name = row.get("name", inst_id.replace("-USDT-SWAP", ""))
            price = row.get("price", row.get("last", 0))
            if inst_id and price:
                coins[inst_id] = {
                    "name": name,
                    "pushed_price": price,
                    "push_time": now,
                    "category": cat,
                }
    return coins


def check_previous_signals(prev_coins: dict[str, dict], current_ids: set[str]) -> list[dict]:
    """检查往期推送币种的当前价格，返回异动列表"""
    alerts = []
    candidates = [
        (iid, info) for iid, info in prev_coins.items()
        if iid not in current_ids
        and info.get("push_time", 0) >= time.time() - TRACKING_TTL_H * 3600
    ]
    if not candidates:
        return alerts

    # 并行拉取当前价格
    def _fetch(iid, info):
        price = fetch_latest_price(iid)
        if price and price > 0:
            old_price = info.get("pushed_price", 0)
            if old_price > 0:
                chg = (price - old_price) / old_price * 100
                if abs(chg) >= TRACKING_CHG_THRESHOLD:
                    return {
                        "instId": iid,
                        "name": info.get("name", iid),
                        "old_price": old_price,
                        "cur_price": price,
                        "chg": chg,
                        "push_time": info.get("push_time", 0),
                        "category": info.get("category", ""),
                    }
        return None

    with ThreadPoolExecutor(max_workers=8) as exe:
        futures = {exe.submit(_fetch, iid, info): iid for iid, info in candidates}
        for fut in as_completed(futures, timeout=30):
            try:
                r = fut.result()
                if r:
                    alerts.append(r)
            except Exception:
                pass

    # 按涨跌幅绝对值排序
    alerts.sort(key=lambda x: abs(x["chg"]), reverse=True)
    return alerts[:8]  # 最多8条


def pick_early_birds(accumulating: list[dict], pre_breakouts: list[dict]) -> list[dict]:
    """从蓄力+突破信号中筛出底部高分币种"""
    candidates = []
    for row in accumulating:
        score = row.get("scoreAccumulating", 0)
        chg = abs(row.get("chg24h", 0))
        if score >= EARLY_BIRD_MIN_SCORE and chg <= EARLY_BIRD_MAX_CHG:
            candidates.append({
                "name": row["instId"].replace("-USDT-SWAP", ""),
                "price": row.get("last", 0),
                "score": score,
                "chg24h": row.get("chg24h", 0),
                "type": "蓄力",
            })
    for row in pre_breakouts:
        score = row.get("scorePreBreakout", 0)
        chg = abs(row.get("chg24h", 0))
        if score >= EARLY_BIRD_MIN_SCORE and chg <= EARLY_BIRD_MAX_CHG:
            candidates.append({
                "name": row["instId"].replace("-USDT-SWAP", ""),
                "price": row.get("last", 0),
                "score": score,
                "chg24h": row.get("chg24h", 0),
                "type": "突破",
            })
    candidates.sort(key=lambda x: x["score"], reverse=True)
    # 按名称去重
    seen_names: set[str] = set()
    unique: list[dict] = []
    for c in candidates:
        if c["name"] not in seen_names:
            seen_names.add(c["name"])
            unique.append(c)
    return unique[:3]


def render_early_bird_section(birds: list[dict]) -> str:
    """渲染早鸟预警区块"""
    if not birds:
        return ""
    lines = ["🔔 早鸟预警（底部高分）", ""]
    for b in birds:
        chg_str = f"{b['chg24h']:+.1f}%"
        lines.append(
            f"  🎯 {b['name']:6s}  \${_fmt(b['price']):10s}  "
            f"评分{b['score']:.0f}  24h{chg_str}  {b['type']}"
        )
    lines.append("")
    # 筹码相关：从蓄力预警数据获取更多信息
    return "\n".join(lines)


def pick_breakout_surges(resurging: list[dict], steady: list[dict]) -> list[dict]:
    """从卷土重来+稳健上涨中筛出强势突破币种（涨幅大且评分高）"""
    candidates = []
    for row in resurging:
        chg = abs(row.get("chg24h", 0))
        score = max(row.get("reSurgeScore", 0), row.get("scoreAccumulating", 0))
        if chg >= BREAKOUT_MIN_CHG and score >= EARLY_BIRD_MIN_SCORE:
            candidates.append({
                "name": row["instId"].replace("-USDT-SWAP", ""),
                "price": row.get("last", 0),
                "chg24h": row.get("chg24h", 0),
                "score": score,
                "type": "卷土重来",
            })
    for row in steady:
        chg = abs(row.get("chg24h", 0))
        if chg >= BREAKOUT_MIN_CHG and row.get("steadyScore", 0) >= EARLY_BIRD_MIN_SCORE:
            candidates.append({
                "name": row["instId"].replace("-USDT-SWAP", ""),
                "price": row.get("last", 0),
                "chg24h": row.get("chg24h", 0),
                "score": row.get("steadyScore", 0),
                "type": "稳健上涨",
            })
    candidates.sort(key=lambda x: abs(x["chg24h"]), reverse=True)
    seen_names: set[str] = set()
    unique: list[dict] = []
    for c in candidates:
        if c["name"] not in seen_names:
            seen_names.add(c["name"])
            unique.append(c)
    return unique[:3]


def render_breakout_section(surges: list[dict]) -> str:
    if not surges:
        return ""
    lines = ["🚨 强势突破（🔥正在拉盘）", ""]
    for s in surges:
        lines.append(
            f"  🚀 {s['name']:6s}  \${_fmt(s['price']):10s}  "
            f"{s['chg24h']:+.1f}%  评分{s['score']:.0f}  {s['type']}"
        )
    lines.append("")
    return "\n".join(lines)


def render_tracking_section(alerts: list[dict]) -> str:
    """渲染往期追踪区块"""
    if not alerts:
        return ""
    lines = ["🔥 往期追踪（异动提醒）", ""]
    for a in alerts:
        arrow = "🚀" if a["chg"] > 0 else "📉"
        direction = "+" if a["chg"] > 0 else ""
        mins_ago = int((time.time() - a["push_time"]) / 60)
        time_str = f"{mins_ago}min前" if mins_ago < 120 else f"{mins_ago//60}h前"
        lines.append(
            f"{arrow} {a['name']}  "
            f"推送价${_fmt(a['old_price'])} → 现价${_fmt(a['cur_price'])}  "
            f"{direction}{a['chg']:.1f}%  [{time_str}/{a['category']}]"
        )
    lines.append("")
    return "\n".join(lines)


def _fmt(v: float) -> str:
    if v >= 100:
        return f"{v:.2f}"
    elif v >= 1:
        return f"{v:.4f}"
    elif v >= 0.01:
        return f"{v:.6f}"
    else:
        return f"{v:.8f}"


def send_openclaw_message(text: str) -> None:
    channel = os.getenv("OPENCLAW_PUSH_CHANNEL", "openclaw-weixin")
    target = os.getenv("OPENCLAW_PUSH_TARGET")
    # 缓存推送内容
    try:
        msg_dir = BASE_DIR / "messages"
        msg_dir.mkdir(parents=True, exist_ok=True)
        record = {"script":"breakout-alerts","time":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"ts":time.time(),"length":len(text),"message":text}
        (msg_dir / "breakout-alerts.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), "utf-8")
    except: pass
    cmd = [
        "openclaw", "message", "send",
        "--channel", channel,
        "--target", target,
        "--message", text,
    ]
    send_timeout = int(os.getenv("OPENCLAW_SEND_TIMEOUT", "60"))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=send_timeout, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"OpenClaw message send failed: {detail}")


def send_dingtalk_webhook(text: str) -> bool:
    """推送到钉钉群 webhook"""
    if not DINGTALK_WEBHOOK:
        return False
    payload = json.dumps({
        "msgtype": "text",
        "text": {"content": text}
    }).encode("utf-8")
    req = Request(DINGTALK_WEBHOOK, data=payload, headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
    })
    try:
        with urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
            if body.get("errcode") != 0:
                print(f"  钉钉推送失败: {body}")
                return False
            return True
    except Exception as e:
        print(f"  钉钉推送异常: {e}")
        return False


def fetch_latest_price(inst_id: str) -> float | None:
    """快速拉取最新价格，超时短"""
    try:
        url = f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}"
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        return float(data["data"][0]["last"])
    except Exception:
        return None


def price_deviation_warning(msg: str) -> str:
    """检查推送前价格是否大幅偏离信号价格，偏离则加上提示"""
    lines = msg.split("\n")
    new_lines = []
    for line in lines:
        # 匹配信号行: "🚀 ENA  $0.11026  +8.23%  稳健上涨"
        parts = line.strip().split()
        if len(parts) >= 3 and parts[0].startswith("🚀") and parts[2].startswith("$"):
            try:
                signal_price = float(parts[2].replace("$", ""))
                symbol = parts[1]
                cur_price = fetch_latest_price(f"{symbol}-USDT-SWAP")
                if cur_price and cur_price > 0:
                    dev = (cur_price - signal_price) / signal_price * 100
                    if abs(dev) >= 3:
                        direction = "📉 已跌" if dev < 0 else "📈 已涨"
                        new_lines.append(f"{line}  ⚠️ {direction} {abs(dev):.1f}%（扫描价 \${signal_price}→现价 \${cur_price:.4f}）")
                        continue
            except (ValueError, IndexError):
                pass
        new_lines.append(line)
    return "\n".join(new_lines)


def main() -> None:
    t0 = time.time()

    # 加载往期追踪状态
    prev_coins = cleanup_tracking_state(load_tracking_state())

    accumulating, pre_breakouts, resurging, steady, watch_list, _ = scan()
    body = render_signals(accumulating, pre_breakouts, resurging, steady, watch_list)

    # 收集本次推送的所有币种（重点推荐从信号列表中产生，已包含）
    current_coins = collect_current_coins(accumulating, pre_breakouts, resurging, steady, watch_list, [])
    current_ids = set(current_coins.keys())

    # 强势突破：涨幅大 + 评分高的币种
    surges = pick_breakout_surges(resurging, steady)
    breakout_section = render_breakout_section(surges)

    # 早鸟预警：底部高分信号
    early_birds = pick_early_birds(accumulating, pre_breakouts)
    early_bird_section = render_early_bird_section(early_birds)

    # 检查往期币种异动
    tracking_alerts = check_previous_signals(prev_coins, current_ids)
    tracking_section = render_tracking_section(tracking_alerts)

    # 合并：早鸟 > 往期追踪 > 当前信号
    if body == "NO_SIGNALS":
        body = "📈 蓄力预警\n\n暂无新增蓄力信号"

    title = os.getenv("CRYPTO_BREAKOUT_TITLE", "加密蓄力预警")
    scan_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    header = f"{title}\n更新时间：{scan_time}\n"
    parts = []
    if breakout_section:
        parts.append(breakout_section)
    if early_bird_section:
        parts.append(early_bird_section)
    if tracking_section:
        parts.append(tracking_section)
    parts.append(body)
    message = header + "\n" + "\n".join(parts) if parts else header + "\n" + body

    # 推送前校验：检查信号币价格是否大幅偏离（只对当前信号部分做）
    message = price_deviation_warning(message)

    print(f"推送耗时: {time.time()-t0:.1f}s")
    send_openclaw_message(message)

    # 保存追踪状态（合并往期+本次）
    merged_coins = dict(prev_coins)
    merged_coins.update(current_coins)
    save_tracking_state(merged_coins)

    # 同步推送到钉钉群
    if DINGTALK_WEBHOOK:
        ok = send_dingtalk_webhook(message)
        print("PUSHED (WX + DD)" if ok else "PUSHED (WX only)")
    else:
        print("PUSHED")


if __name__ == "__main__":
    main()
