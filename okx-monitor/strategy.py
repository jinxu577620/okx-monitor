from __future__ import annotations

from statistics import mean


def sma(values, period: int):
    if len(values) < period:
        return None
    return mean(values[-period:])


def calc_levels(candles):
    highs = [x["high"] for x in candles[-20:]]
    lows = [x["low"] for x in candles[-20:]]
    return {
        "resistance": max(highs) if highs else None,
        "support": min(lows) if lows else None,
    }


def analyze_trend(candles):
    closes = [x["close"] for x in candles]
    if len(closes) < 20:
        return {"bias": "数据不足", "ma20": None, "ma60": None}

    ma20 = sma(closes, 20)
    ma60 = sma(closes, 60) if len(closes) >= 60 else None
    last = closes[-1]

    if ma60 is not None:
        if last > ma20 > ma60:
            bias = "偏多"
        elif last < ma20 < ma60:
            bias = "偏空"
        else:
            bias = "震荡"
    else:
        bias = "偏多" if last > ma20 else "偏空"

    return {
        "bias": bias,
        "last": last,
        "ma20": ma20,
        "ma60": ma60,
    }


def build_trade_plan(candles):
    trend = analyze_trend(candles)
    levels = calc_levels(candles)
    last = trend.get("last")
    support = levels.get("support")
    resistance = levels.get("resistance")

    if not last or support is None or resistance is None:
        return {"trigger_long": None, "trigger_short": None, "stop": None}

    long_trigger = round(resistance * 1.002, 2)
    short_trigger = round(support * 0.998, 2)
    stop_long = round(support * 0.995, 2)
    stop_short = round(resistance * 1.005, 2)

    if trend.get("bias") == "偏多":
        summary = "日内偏多，优先等突破或回踩确认，不追高。"
    elif trend.get("bias") == "偏空":
        summary = "日内偏空，优先等反抽失败或支撑跌破，不抄底。"
    else:
        summary = "当前更像震荡，先等关键位突破后再动手。"

    return {
        "trigger_long": long_trigger,
        "trigger_short": short_trigger,
        "stop_long": stop_long,
        "stop_short": stop_short,
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "summary": summary,
    }
