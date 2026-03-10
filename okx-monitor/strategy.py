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

    return {
        "trigger_long": round(resistance * 1.002, 2),
        "trigger_short": round(support * 0.998, 2),
        "stop_long": round(support * 0.995, 2),
        "stop_short": round(resistance * 1.005, 2),
    }
