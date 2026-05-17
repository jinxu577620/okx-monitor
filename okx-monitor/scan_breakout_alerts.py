from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from okx_retry import okx_get_json

# 信号类型权重（越高越值得入场）
SIGNAL_WEIGHTS = {"突破在即": 5, "卷土重来": 4, "稳健上涨": 3, "蓄力中": 2}

BASE_URL = "https://www.okx.com"
HEADERS = {"User-Agent": "Mozilla/5.0"}
TOP_N = 50  # 2026-05-06 优化：从25扩大到50，覆盖更多小币，避免漏掉起爆初期信号
MAX_ACCUMULATING = 5
MAX_PRE_BREAKOUT = 3
MAX_RESURGE = 3
MAX_STEADY = 5
MAX_WORKERS = 20  # 2026-05-06 覆盖币种从33扩到65，提高并行度
STATE_FILE = Path(__file__).resolve().parent / "scan_breakout_state.json"


def safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(data: dict) -> None:
    STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_json(path: str, params: dict, timeout: int = 20) -> dict:
    return okx_get_json(f"{BASE_URL}{path}", params=params, headers=HEADERS, timeout=timeout)


def fetch_swap_tickers() -> list[dict]:
    data = get_json("/api/v5/market/tickers", {"instType": "SWAP"})
    return data.get("data", [])


def fetch_candles(inst_id: str, bar: str, limit: int) -> list[dict]:
    data = get_json("/api/v5/market/candles", {"instId": inst_id, "bar": bar, "limit": str(limit)})
    rows = data.get("data", [])
    out = []
    for row in rows:
        out.append(
            {
                "ts": int(row[0]),
                "open": safe_float(row[1]),
                "high": safe_float(row[2]),
                "low": safe_float(row[3]),
                "close": safe_float(row[4]),
                "volume": safe_float(row[5]),
            }
        )
    out.reverse()
    return out


def fetch_oi(inst_id: str) -> float:
    try:
        data = get_json("/api/v5/public/open-interest", {"instId": inst_id})
    except Exception:
        return 0.0
    row = (data.get("data") or [{}])[0]
    return safe_float(row.get("oiUsd"))


def fetch_funding(inst_id: str) -> float | None:
    try:
        data = get_json("/api/v5/public/funding-rate", {"instId": inst_id})
    except Exception:
        return None
    try:
        return float((data.get("data") or [{}])[0].get("fundingRate"))
    except Exception:
        return None


def pct_change(new: float, old: float) -> float:
    if not old:
        return 0.0
    return (new - old) / old * 100


def pick_universe() -> list[dict]:
    rows = []
    for row in fetch_swap_tickers():
        inst_id = row.get("instId", "")
        if not inst_id.endswith("-USDT-SWAP"):
            continue
        last = safe_float(row.get("last"))
        open24h = safe_float(row.get("open24h"))
        vol_ccy = safe_float(row.get("volCcy24h"))
        notional_24h = last * vol_ccy
        change24h = pct_change(last, open24h) if open24h else 0.0
        if notional_24h <= 1_000_000:
            continue
        rows.append(
            {
                "instId": inst_id,
                "last": last,
                "notional24h": notional_24h,
                "change24h": change24h,
            }
        )
    rows.sort(key=lambda x: x["notional24h"], reverse=True)
    top_vol = rows[:TOP_N]
    extras = [r for r in rows if r["change24h"] >= 3 and r not in top_vol][:15]  # 2026-05-06：涨幅门槛从5降到3，数量从8扩到15
    return top_vol + extras


def evaluate_inst(inst_id: str, prev_state: dict) -> dict | None:
    candles_15m = fetch_candles(inst_id, "15m", 32)
    candles_1h = fetch_candles(inst_id, "1H", 26)
    if len(candles_15m) < 24 or len(candles_1h) < 20:
        return None

    latest_15m = candles_15m[-1]
    prev_15m = candles_15m[-2]
    latest_1h = candles_1h[-1]
    prev_1h = candles_1h[-2]

    base_15m = candles_15m[-21:-5]
    trigger_15m = candles_15m[-5:-1]
    trend_1h = candles_1h[-13:-1]

    base_high = max(x["high"] for x in base_15m)
    base_low = min(x["low"] for x in base_15m)
    trigger_high = max(x["high"] for x in trigger_15m)
    avg_vol_15m = sum(x["volume"] for x in base_15m[-8:]) / min(8, len(base_15m))
    avg_vol_1h = sum(x["volume"] for x in trend_1h[-6:]) / min(6, len(trend_1h))
    trend_high_1h = max(x["high"] for x in trend_1h[-6:])

    base_range_pct = pct_change(base_high, base_low)
    price_chg_15m = pct_change(latest_15m["close"], prev_15m["close"])
    price_chg_1h = pct_change(latest_1h["close"], prev_1h["close"])
    breakout_pct_15m = pct_change(latest_15m["close"], trigger_high)
    near_breakout_pct = pct_change(latest_15m["close"], trigger_high)
    extension_from_base = pct_change(latest_15m["close"], base_low)
    vol_ratio_15m = (latest_15m["volume"] / avg_vol_15m) if avg_vol_15m else 0.0
    vol_ratio_1h = (latest_1h["volume"] / avg_vol_1h) if avg_vol_1h else 0.0

    # 24h 涨幅（从1h K线算）
    chg_24h = 0.0
    if len(candles_1h) >= 24:
        chg_24h = pct_change(latest_1h["close"], candles_1h[-24]["close"])

    funding = fetch_funding(inst_id)
    oi_usd = fetch_oi(inst_id)
    prev_row = prev_state.get(inst_id, {})
    prev_oi_usd = safe_float(prev_row.get("oiUsd"))
    oi_chg_run = pct_change(oi_usd, prev_oi_usd) if prev_oi_usd else 0.0

    candidate_ts = int(prev_row.get("last_candidate_ts", 0) or 0)
    breakout_ts = int(prev_row.get("last_breakout_ts", 0) or 0)
    surge_ts = int(prev_row.get("last_surge_ts", 0) or 0)

    # ---- 蓄力预警（暴涨前） ----
    # 核心：窄幅横盘 + 成交量在底部悄悄放大 + OI增加 + 价格没怎么涨
    # 不要求已经突破或拉涨，只找蓄势待发的
    is_tight_base = 0 < base_range_pct <= 25  # 放宽到25%，让更多币进来
    is_not_too_extended = extension_from_base <= 30  # 从底部涨不超过30%
    is_funding_ok = funding is None or funding <= 0.002  # 费率容忍度放宽
    is_oi_building = oi_chg_run >= 0.8  # OI只要在增加就行，门槛降低
    is_15m_volume = vol_ratio_15m >= 1.2  # 15m量比 >= 1.2x 就算放量（之前1.6）
    is_1h_volume = vol_ratio_1h >= 1.0
    is_15m_impulse = price_chg_15m >= 0.4  # 稍有脉冲即可，不需要大涨
    is_1h_trend = price_chg_1h >= 0.6
    is_near_breakout = latest_15m["close"] >= trigger_high * 0.985  # 离突破位1.5%以内就算逼近
    is_breakout = latest_15m["close"] > trigger_high * 1.003
    is_1h_confirm = latest_1h["close"] > trend_high_1h * 0.995

    # 蓄力得分：主要看蓄势条件（横盘+量+OI），价格涨幅只是加分项
    score_accumulating = 0.0
    if is_tight_base:
        score_accumulating += 2.0
    if is_not_too_extended:
        score_accumulating += 1.5
    if is_15m_volume:
        score_accumulating += min(vol_ratio_15m * 0.8, 3.0)
    if is_oi_building:
        score_accumulating += min(oi_chg_run * 1.5, 3.0)
    if is_funding_ok:
        score_accumulating += 0.5
    if is_1h_volume:
        score_accumulating += min(vol_ratio_1h * 0.5, 1.5)
    if is_15m_impulse:
        score_accumulating += min(price_chg_15m, 2.0)
    if is_near_breakout:
        score_accumulating += 2.0
    # 确认条件：突破在即
    score_pre_breakout = score_accumulating
    if is_breakout:
        score_pre_breakout += 3.0
    if is_1h_trend:
        score_pre_breakout += min(price_chg_1h, 2.0)
    if is_1h_confirm:
        score_pre_breakout += 1.0

    # ---- 卷土重来检测（已经涨过的回调后卷土重来） ----
    candles_1m = fetch_candles(inst_id, "1m", 12)
    re_surge_score = 0.0
    chg_5m = 0.0
    vol_ratio_1m = 0.0
    surge_range_5m = 0.0
    if len(candles_1m) >= 6:
        recent_1m = candles_1m[-5:]
        older_1m = candles_1m[:-5]
        high_1m = max(x["high"] for x in recent_1m)
        low_1m = min(x["low"] for x in recent_1m)
        vol_1m_sum = sum(x["volume"] for x in recent_1m)
        avg_vol_1m = sum(x["volume"] for x in older_1m) / max(len(older_1m), 1)
        surge_range_5m = pct_change(high_1m, low_1m)
        vol_ratio_1m = vol_1m_sum / avg_vol_1m if avg_vol_1m > 0 else 0.0
        open_5m = recent_1m[0]["open"]
        close_now = recent_1m[-1]["close"]
        chg_5m = pct_change(close_now, open_5m)

        if chg_5m >= 1.0:
            re_surge_score += min(chg_5m * 1.5, 5.0)
        if vol_ratio_1m >= 2.0:
            re_surge_score += min(vol_ratio_1m * 0.8, 4.0)
        if oi_chg_run >= 2.0:
            re_surge_score += min(oi_chg_run * 0.6, 3.0)

    if price_chg_15m >= 3.0:
        re_surge_score += min(price_chg_15m * 0.5, 4.0)
    if vol_ratio_15m >= 2.0:
        re_surge_score += min(vol_ratio_15m * 0.5, 3.0)
    if funding is not None and funding >= 0.001:
        re_surge_score -= 1.0

    # ---- 稳健上涨检测 ----
    # 不看蓄势形态，关注已经涨了但还在涨、形态健康的票
    # PENDLE 这种 +9% 稳稳涨的就该被发现
    steady_score = 0.0
    # 24h 涨幅
    if price_chg_1h >= 1.0:
        steady_score += min(price_chg_1h * 1.5, 5.0)
    # 15m 涨幅
    if price_chg_15m >= 0.3:
        steady_score += min(price_chg_15m * 2.0, 3.0)
    # 量比正常（不放量也可以，温和放量就行）
    if vol_ratio_1h >= 0.8:
        steady_score += min(vol_ratio_1h * 1.5, 3.0)
    if vol_ratio_15m >= 0.5:
        steady_score += min(vol_ratio_15m, 2.0)
    # OI 在增加最好
    if oi_chg_run >= 0.5:
        steady_score += min(oi_chg_run * 2.0, 3.0)
    # 距离太高会扣分
    if extension_from_base > 50:
        steady_score -= 2.0
    # 费率太高扣分
    if funding is not None and funding >= 0.001:
        steady_score -= 1.0
    # 底部有蓄势加分
    if is_tight_base:
        steady_score += 2.0
    # 接近突破位加分
    if is_near_breakout:
        steady_score += 2.0

    # ---- 四个信号级别 ----
    current_ts = latest_15m["ts"]
    # 蓄力级：看起来要动了，提前盯
    accumulating_ready = (
        score_accumulating >= 7.5  # 门槛调低，更多蓄力币被发现
        and (is_near_breakout or (is_15m_volume and is_oi_building))  # 接近突破 或 放量+OI增加都算蓄力
        and current_ts > candidate_ts
    )
    # 预突破级：万事俱备，就差一根阳线（现在等于蓄力+已突破）
    pre_breakout_ready = (
        score_pre_breakout >= 10.0
        and is_breakout
        and current_ts > breakout_ts
    )
    # 卷土重来级：正在动但之前没抓到
    re_surge_ready = (
        re_surge_score >= 7.0
        and current_ts > surge_ts
    )
    # 稳健上涨级：温和但持续的涨势，不要求量/形态
    # 核心条件：价格必须在涨或持平，排除已经回落、MA乖离过大的
    # 优化 2026-05-06：15m可以接受小幅回调（-3%以内），1h放宽到-1%，避免漏掉刚回调完的起爆
    is_steady_trending = (price_chg_15m >= -3.0 and price_chg_1h >= -1.0)  # 15m允许小幅回调
    steady_ready = (
        steady_score >= 8.0
        and is_steady_trending
        and current_ts > surge_ts  # 跟卷土重来共用冷却
    )

    return {
        "instId": inst_id,
        "last": latest_15m["close"],
        "ts": current_ts,
        "oiUsd": oi_usd,
        "chg24h": chg_24h,
        "priceChg15m": price_chg_15m,
        "priceChg1h": price_chg_1h,
        "nearBreakoutPct": near_breakout_pct,
        "breakoutPct15m": breakout_pct_15m,
        "baseRangePct": base_range_pct,
        "extensionFromBase": extension_from_base,
        "volRatio15m": vol_ratio_15m,
        "volRatio1h": vol_ratio_1h,
        "oiChgRun": oi_chg_run,
        "fundingRate": funding,
        "scoreAccumulating": score_accumulating,
        "scorePreBreakout": score_pre_breakout,
        "reSurgeScore": re_surge_score,
        "steadyScore": steady_score,
        "surgeRange5m": surge_range_5m,
        "volRatio1m": vol_ratio_1m,
        "accumulatingAlert": accumulating_ready,
        "preBreakoutAlert": pre_breakout_ready,
        "reSurgeAlert": re_surge_ready,
        "steadyAlert": steady_ready,
    }


def scan() -> tuple[list[dict], list[dict], list[dict], list[dict], dict]:
    """
    返回值: (蓄力中, 突破在即, 卷土重来, 稳健上涨, 待观察高分列表, state)
    """
    prev_state = load_state()
    next_state = {}
    accumulating = []
    pre_breakouts = []
    resurging = []
    steady = []

    universe = pick_universe()
    # 并行评估
    results = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exe:
        fut_map = {}
        for item in universe:
            inst_id = item["instId"]
            fut = exe.submit(evaluate_inst, inst_id, prev_state)
            fut_map[fut] = inst_id
        for fut in as_completed(fut_map, timeout=90):
            inst_id = fut_map[fut]
            try:
                r = fut.result()
            except Exception:
                continue
            if r:
                results[inst_id] = r

    for item in universe:
        inst_id = item["instId"]
        result = results.get(inst_id)
        if not result:
            continue
        prev_row = prev_state.get(inst_id, {})
        state_row = {
            "oiUsd": result["oiUsd"],
            "last_candidate_ts": prev_row.get("last_candidate_ts", 0),
            "last_breakout_ts": prev_row.get("last_breakout_ts", 0),
            "last_surge_ts": prev_row.get("last_surge_ts", 0),
        }
        if result["accumulatingAlert"]:
            accumulating.append(result)
            state_row["last_candidate_ts"] = result["ts"]
        if result["preBreakoutAlert"]:
            pre_breakouts.append(result)
            state_row["last_breakout_ts"] = result["ts"]
        if result["reSurgeAlert"]:
            resurging.append(result)
            state_row["last_surge_ts"] = result["ts"]
        if result["steadyAlert"]:
            steady.append(result)
            state_row["last_surge_ts"] = result["ts"]
        next_state[inst_id] = state_row

    save_state(next_state)
    # 收集被涨幅过滤但评分高的待观察币（供观察清单用）
    high_score_watch = []
    seen_ids = set(r["instId"] for r in accumulating + pre_breakouts + resurging + steady)
    for inst_id, result in results.items():
        if inst_id in seen_ids:
            continue
        # 评分高但被过滤的币
        top_score = max(
            result.get("scoreAccumulating", 0),
            result.get("scorePreBreakout", 0),
            result.get("reSurgeScore", 0),
            result.get("steadyScore", 0),
        )
        if top_score >= 7.0:
            high_score_watch.append(result)

    high_score_watch.sort(key=lambda x: -max(
        x.get("scoreAccumulating", 0),
        x.get("scorePreBreakout", 0),
        x.get("reSurgeScore", 0),
        x.get("steadyScore", 0),
    ))

    accumulating.sort(key=lambda x: x["scoreAccumulating"], reverse=True)
    pre_breakouts.sort(key=lambda x: x["scorePreBreakout"], reverse=True)
    resurging.sort(key=lambda x: x["reSurgeScore"], reverse=True)
    steady.sort(key=lambda x: x["steadyScore"], reverse=True)
    return accumulating[:MAX_ACCUMULATING], pre_breakouts[:MAX_PRE_BREAKOUT], resurging[:MAX_RESURGE], steady[:MAX_STEADY], high_score_watch[:5], next_state


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:.1f}%"


def fmt_rate(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value * 100:.3f}%"


def fmt_price(value: float) -> str:
    if value >= 100:
        return str(round(value, 2))
    if value >= 1:
        return str(round(value, 4))
    return str(round(value, 6))


# 24h 涨幅过滤（按信号类型区别对待）
# 蓄力中/稳健上涨：涨太多就不推了（已错过最佳时机）
# 卷土重来/突破在即：即使涨了很多，只要动能在就可以追
# 优化 2026-05-06：提高阈值，避免漏掉已起爆的高分币
MAX_CHG_KEEP = 30.0      # 蓄力中/稳健上涨超过此值不推（提高至30%，以防漏掉起爆信号）
MAX_CHG_RESURGE = 60.0   # 卷土重来/突破在即使放宽至此值

def _calc_entries(price: float, signal_type: str) -> dict:
    """根据信号类型计算多档止盈止损"""
    price_f = float(price)
    # 不同信号类型用不同的止盈系数
    if signal_type in ("卷土重来", "突破在即"):
        # 已经在动了，惯性大，止盈拉远
        tp_factors = [0.06, 0.15, 0.25]
        sl_factor = 0.04  # 止损紧一点
    elif signal_type == "稳健上涨":
        tp_factors = [0.05, 0.12, 0.20]
        sl_factor = 0.05
    else:  # 蓄力中
        tp_factors = [0.04, 0.10, 0.18]
        sl_factor = 0.05

    return {
        "tp1": price_f * (1 + tp_factors[0]),
        "tp2": price_f * (1 + tp_factors[1]),
        "tp3": price_f * (1 + tp_factors[2]),
        "sl": price_f * (1 - sl_factor),
    }


def _fmt_entry_line(name: str, price: float, chg_24h: float, signal_type: str) -> str:
    """格式化成完整信号卡片（带多档止盈）"""
    entries = _calc_entries(price, signal_type)
    price_str = fmt_price(price)
    tp1_str = fmt_price(entries["tp1"])
    tp2_str = fmt_price(entries["tp2"])
    tp3_str = fmt_price(entries["tp3"])
    sl_str = fmt_price(entries["sl"])
    
    tp1_pct = (entries["tp1"] / price - 1) * 100
    tp2_pct = (entries["tp2"] / price - 1) * 100
    tp3_pct = (entries["tp3"] / price - 1) * 100
    sl_pct = (entries["sl"] / price - 1) * 100
    
    return (
        f"🚀 {name}  ${price_str}  +{chg_24h:.2f}%  {signal_type}\n"
        f"  TP1 ${tp1_str} (+{tp1_pct:.1f}%) | TP2 ${tp2_str} (+{tp2_pct:.1f}%) | TP3 ${tp3_str} (+{tp3_pct:.1f}%)\n"
        f"  止损 ${sl_str} ({sl_pct:.1f}%)"
    )


def deep_rank_top2(all_signals: list[dict]) -> list[dict]:
    """
    对推送列表里的币做深度分析（盘口深度、资金费率、OI变化），
    选出综合评分最高的2个入场推荐。
    评分权重：信号类型 > 盘口深度 > 涨幅潜力 > 资金费率健康度 > OI
    """
    if not all_signals:
        return []

    enriched = []
    with ThreadPoolExecutor(max_workers=8) as exe:
        fut_map = {}
        for row in all_signals:
            inst_id = row["instId"]
            fut = exe.submit(_fetch_depth_data, inst_id)
            fut_map[fut] = row
        for fut in as_completed(fut_map, timeout=45):
            row = fut_map[fut]
            try:
                depth = fut.result()
            except Exception:
                depth = {}

            # 信号权重分
            sig_type = row.get("_signalType", "蓄力中")
            sig_score = SIGNAL_WEIGHTS.get(sig_type, 2)

            # 涨幅潜力分：涨得少的币空间更大（小于10%加分）
            chg = abs(row.get("chg24h", 0))
            if chg < 5:
                potential_score = 5
            elif chg < 10:
                potential_score = 4
            elif chg < 20:
                potential_score = 3
            elif chg < 30:
                potential_score = 2
            else:
                potential_score = 1

            # 盘口深度分：买卖盘均衡 + 价差小 = 流动性好
            bid_vol = depth.get("bidVolUsd", 0)
            ask_vol = depth.get("askVolUsd", 0)
            spread = depth.get("spreadPct", 1)
            liq_score = 0
            if bid_vol > 50000 and ask_vol > 50000:
                liq_score = 3
            elif bid_vol > 10000 and ask_vol > 10000:
                liq_score = 2
            elif bid_vol > 1000 or ask_vol > 1000:
                liq_score = 1
            # 价差太小扣分
            if spread < 0.05:
                liq_score += 1

            # 资金费率分：负费率表示做多成本低
            fr = depth.get("fundingRate", 0)
            if fr < -0.01:
                fr_score = 3  # 负费率，做多成本低
            elif fr < 0:
                fr_score = 2
            elif fr < 0.01:
                fr_score = 1
            else:
                fr_score = 0  # 正费率，做多贵

            total = sig_score * 3 + potential_score * 2 + liq_score * 2 + fr_score * 1

            enriched.append({
                "instId": row["instId"],
                "name": row["instId"].replace("-USDT-SWAP", ""),
                "price": row["last"],
                "chg24h": row["chg24h"],
                "signalType": sig_type,
                "score": total,
                "depth": depth,
                "reason": _build_reason(sig_type, chg, fr, spread, bid_vol, ask_vol),
            })

    # 按 instId 去重，保留每个币种最高分的那组信号
    seen_ids: set[str] = set()
    unique: list[dict] = []
    enriched.sort(key=lambda x: -x["score"])
    for e in enriched:
        iid = e.get("instId", "")
        if iid and iid not in seen_ids:
            seen_ids.add(iid)
            unique.append(e)
    return unique[:2]


def _fetch_depth_data(inst_id: str) -> dict:
    """拉取一个币的盘口深度和资金费率"""
    result = {"bidVolUsd": 0, "askVolUsd": 0, "spreadPct": 1, "fundingRate": 0}
    try:
        # 盘口深度
        ob = okx_get_json(
            "https://www.okx.com/api/v5/market/books",
            {"instId": inst_id, "sz": "10"},
            timeout=10, max_retries=1, backoff_base=0.3,
        )
        data = ob.get("data", [{}])[0]
        bids = data.get("bids", [])
        asks = data.get("asks", [])
        if bids and asks:
            bid_vol = sum(float(b[1]) * float(b[0]) for b in bids)
            ask_vol = sum(float(a[1]) * float(a[0]) for a in asks)
            spread = (float(asks[0][0]) - float(bids[0][0])) / float(bids[0][0]) * 100
            result["bidVolUsd"] = bid_vol
            result["askVolUsd"] = ask_vol
            result["spreadPct"] = spread
    except Exception:
        pass

    try:
        # 资金费率
        fr = okx_get_json(
            "https://www.okx.com/api/v5/public/funding-rate",
            {"instId": inst_id},
            timeout=10, max_retries=1, backoff_base=0.3,
        )
        fr_data = fr.get("data", [{}])[0]
        result["fundingRate"] = float(fr_data.get("fundingRate", 0)) * 100
    except Exception:
        pass

    return result


def _build_reason(sig_type: str, chg: float, fr: float, spread: float, bid_vol: float, ask_vol: float) -> str:
    """生成推荐理由"""
    parts = []
    # 信号理由
    if sig_type == "突破在即":
        parts.append("突破信号强")
    elif sig_type == "卷土重来":
        parts.append("卷土重来动能足")
    elif sig_type == "稳健上涨":
        parts.append("上涨趋势稳健")
    else:
        parts.append("蓄力待突破")

    # 涨幅理由
    if chg < 5:
        parts.append("刚启动空间大")
    elif chg < 10:
        parts.append("涨幅适中")

    # 资金费率理由
    if fr < -0.01:
        parts.append("做多成本低")
    elif fr < 0:
        parts.append("费率偏多")

    # 流动性理由
    if bid_vol > 50000 and ask_vol > 50000:
        parts.append("流动性极好")
    elif bid_vol > 10000 and ask_vol > 10000:
        parts.append("流动性良好")

    if spread < 0.03:
        parts.append("滑点低")

    return "，".join(parts) if parts else "综合评分高"



def render_signals(accumulating: list[dict], pre_breakouts: list[dict], resurging: list[dict], steady: list[dict], watch_list: list[dict] | None = None) -> str:
    lines = ["📈 蓄力预警", ""]
    had_any = False

    for row in resurging:
        if abs(row['chg24h']) >= MAX_CHG_RESURGE:
            continue
        name = row['instId'].replace('-USDT-SWAP','')
        lines.append(_fmt_entry_line(name, row['last'], row['chg24h'], "卷土重来"))
        lines.append("")
        had_any = True

    for row in steady:
        if abs(row['chg24h']) >= MAX_CHG_KEEP:
            continue
        name = row['instId'].replace('-USDT-SWAP','')
        lines.append(_fmt_entry_line(name, row['last'], row['chg24h'], "稳健上涨"))
        lines.append("")
        had_any = True

    for row in pre_breakouts:
        if abs(row['chg24h']) >= MAX_CHG_RESURGE:
            continue
        name = row['instId'].replace('-USDT-SWAP','')
        lines.append(_fmt_entry_line(name, row['last'], row['chg24h'], "突破在即"))
        lines.append("")
        had_any = True

    for row in accumulating:
        if abs(row['chg24h']) >= MAX_CHG_KEEP:
            continue
        name = row['instId'].replace('-USDT-SWAP','')
        # 蓄力中还没动，保守点，只给观察提示不带止盈
        lines.append(f"💤 {name}  ${fmt_price(row['last'])}  +{row['chg24h']:.2f}%  蓄力中（待突破确认）")
        lines.append("")
        had_any = True

    # 观察清单：评分高但被涨幅过滤的（已起爆，等回调）
    if watch_list:
        lines.append("📌 观察清单（高分等回调）")
        lines.append("")
        for row in watch_list:
            name = row['instId'].replace('-USDT-SWAP','')
            chg = row['chg24h']
            all_scores = {
                '蓄力': row.get('scoreAccumulating', 0),
                '突破': row.get('scorePreBreakout', 0),
                '卷土': row.get('reSurgeScore', 0),
                '稳健': row.get('steadyScore', 0),
            }
            best_label = max(all_scores, key=all_scores.get)
            best_score = all_scores[best_label]
            lines.append(f"  {name}  ${fmt_price(row['last'])}  +{chg:.2f}%  {best_label}{best_score:.0f}分  ⏳等回调")
            had_any = True

    if not had_any:
        return "NO_SIGNALS"

    # === 深度TOP2推荐：收集所有信号币进行深度评分 ===
    # 给每个信号币标注信号类型
    all_signals = []
    for row in resurging:
        if abs(row['chg24h']) >= MAX_CHG_RESURGE:
            continue
        row = dict(row)
        row["_signalType"] = "卷土重来"
        all_signals.append(row)
    for row in steady:
        if abs(row['chg24h']) >= MAX_CHG_KEEP:
            continue
        row = dict(row)
        row["_signalType"] = "稳健上涨"
        all_signals.append(row)
    for row in pre_breakouts:
        if abs(row['chg24h']) >= MAX_CHG_RESURGE:
            continue
        row = dict(row)
        row["_signalType"] = "突破在即"
        all_signals.append(row)
    for row in accumulating:
        if abs(row['chg24h']) >= MAX_CHG_KEEP:
            continue
        row = dict(row)
        row["_signalType"] = "蓄力中"
        all_signals.append(row)

    top2 = deep_rank_top2(all_signals)
    if top2:
        lines.append("")
        lines.append("🎯 重点推荐 TOP2")
        lines.append("")
        for i, rec in enumerate(top2, 1):
            fr_str = "{:.3f}%".format(rec["depth"].get("fundingRate", 0))
            lines.append(
                "{}. {}  ${:.4f}  +{:.2f}%  {}  (评分{:.0f})".format(
                    i, rec["name"], rec["price"], rec["chg24h"],
                    rec["signalType"], rec["score"]
                )
            )
            lines.append("    {} | 盘口买${:.0f}/卖${:.0f} | 费率{}".format(
                rec["reason"],
                rec["depth"].get("bidVolUsd", 0),
                rec["depth"].get("askVolUsd", 0),
                fr_str,
            ))
            lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    a, p, r, s, w, _ = scan()
    print(render_signals(a, p, r, s, w))
