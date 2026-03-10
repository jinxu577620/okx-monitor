from __future__ import annotations

from statistics import mean, pstdev


def sma(values, period: int):
    if len(values) < period:
        return None
    return mean(values[-period:])


def ema(values, period: int):
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    ema_val = mean(values[:period])
    for price in values[period:]:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val


def rsi(values, period: int = 14):
    if len(values) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))
    avg_gain = mean(gains[-period:])
    avg_loss = mean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def bollinger(values, period: int = 20, std_mult: float = 2.0):
    if len(values) < period:
        return None
    basis = mean(values[-period:])
    dev = pstdev(values[-period:])
    upper = basis + std_mult * dev
    lower = basis - std_mult * dev
    return {"mid": basis, "upper": upper, "lower": lower}


def calc_levels(candles):
    highs = [x["high"] for x in candles[-20:]]
    lows = [x["low"] for x in candles[-20:]]
    return {
        "resistance": max(highs) if highs else None,
        "support": min(lows) if lows else None,
    }


def analyze_trend(candles):
    closes = [x["close"] for x in candles]
    volumes = [x["volume"] for x in candles]
    if len(closes) < 20:
        return {"bias": "数据不足", "ma20": None, "ma60": None}

    ma20 = sma(closes, 20)
    ma60 = sma(closes, 60) if len(closes) >= 60 else None
    last = closes[-1]
    last_vol = volumes[-1] if volumes else None
    avg_vol20 = sma(volumes, 20) if len(volumes) >= 20 else None
    rsi14 = rsi(closes, 14)
    boll = bollinger(closes, 20, 2.0)
    macd_fast = ema(closes, 12)
    macd_slow = ema(closes, 26)
    macd_val = macd_fast - macd_slow if macd_fast is not None and macd_slow is not None else None

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
        "rsi14": rsi14,
        "boll": boll,
        "last_vol": last_vol,
        "avg_vol20": avg_vol20,
        "macd": macd_val,
    }


def score_signal(trend: dict):
    score = 0
    reasons = []
    last = trend.get("last")
    ma20 = trend.get("ma20")
    ma60 = trend.get("ma60")
    rsi14 = trend.get("rsi14")
    boll = trend.get("boll")
    last_vol = trend.get("last_vol")
    avg_vol20 = trend.get("avg_vol20")
    macd_val = trend.get("macd")

    if ma20 is not None and ma60 is not None:
        if last > ma20 > ma60:
            score += 2
            reasons.append("均线多头排列")
        elif last < ma20 < ma60:
            score -= 2
            reasons.append("均线空头排列")

    if rsi14 is not None:
        if 55 <= rsi14 <= 70:
            score += 1
            reasons.append("RSI 偏强但未过热")
        elif 30 <= rsi14 <= 45:
            score -= 1
            reasons.append("RSI 偏弱")
        elif rsi14 > 75:
            score -= 1
            reasons.append("RSI 过热，提防回落")
        elif rsi14 < 25:
            score += 1
            reasons.append("RSI 偏低，注意技术反弹")

    if boll:
        if last > boll["upper"]:
            score += 1
            reasons.append("价格站上布林上轨")
        elif last < boll["lower"]:
            score -= 1
            reasons.append("价格跌破布林下轨")
        elif last > boll["mid"]:
            score += 0.5
            reasons.append("价格位于布林中轨上方")
        else:
            score -= 0.5
            reasons.append("价格位于布林中轨下方")

    if last_vol is not None and avg_vol20:
        if last_vol > avg_vol20 * 1.4:
            score += 1
            reasons.append("成交量明显放大")
        elif last_vol < avg_vol20 * 0.7:
            score -= 0.5
            reasons.append("成交量偏弱")

    if macd_val is not None:
        if macd_val > 0:
            score += 1
            reasons.append("MACD 位于零轴上方")
        elif macd_val < 0:
            score -= 1
            reasons.append("MACD 位于零轴下方")

    if score >= 3:
        signal = "偏多"
    elif score <= -3:
        signal = "偏空"
    else:
        signal = "观望"

    return {"score": round(score, 2), "signal": signal, "reasons": reasons[:4]}


def build_trade_plan(candles):
    trend = analyze_trend(candles)
    levels = calc_levels(candles)
    signal = score_signal(trend)
    last = trend.get("last")
    support = levels.get("support")
    resistance = levels.get("resistance")

    if not last or support is None or resistance is None:
        return {"trigger_long": None, "trigger_short": None, "stop": None}

    long_trigger = round(resistance * 1.002, 2)
    short_trigger = round(support * 0.998, 2)
    stop_long = round(support * 0.995, 2)
    stop_short = round(resistance * 1.005, 2)

    if signal["signal"] == "偏多":
        summary = "多指标偏多，可优先等突破或回踩确认后做多。"
    elif signal["signal"] == "偏空":
        summary = "多指标偏空，优先等反抽失败或破位后做空。"
    else:
        summary = "多空信号分歧较大，先观望，等关键位突破。"

    return {
        "trigger_long": long_trigger,
        "trigger_short": short_trigger,
        "stop_long": stop_long,
        "stop_short": stop_short,
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "summary": summary,
        "signal": signal["signal"],
        "score": signal["score"],
        "reasons": signal["reasons"],
        "rsi14": trend.get("rsi14"),
        "boll": trend.get("boll"),
        "avg_vol20": trend.get("avg_vol20"),
        "last_vol": trend.get("last_vol"),
        "macd": trend.get("macd"),
    }
