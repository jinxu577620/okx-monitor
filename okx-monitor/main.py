from __future__ import annotations

from datetime import datetime

from config import WATCHLIST, BAR_MAP
from okx_public import OKXPublicClient
from report import build_symbol_report, build_report
from state import load_state, save_state, push_history
from strategy import analyze_trend, build_trade_plan


def calc_market_extras(client: OKXPublicClient, inst_id: str, ticker: dict, candles_4h: list[dict], state: dict):
    funding = client.get_funding_rate(inst_id)
    oi_now = client.get_open_interest(inst_id)

    prev = state.get(inst_id, {})
    prev_oi = prev.get("oi")
    prev_last = prev.get("last")
    prev_vol24h = prev.get("vol24h")
    history = prev.get("history", [])

    oi = oi_now.get("oi")
    oi_delta_pct = None
    if prev_oi and oi:
        try:
            oi_delta_pct = ((oi - prev_oi) / prev_oi) * 100
        except ZeroDivisionError:
            oi_delta_pct = None

    flow_bias = None
    last = ticker.get("last")
    bid = ticker.get("bidPx")
    ask = ticker.get("askPx")
    if last and bid and ask:
        mid = (bid + ask) / 2
        if last >= mid and oi_delta_pct is not None and oi_delta_pct >= 0:
            flow_bias = "inflow"
        elif last < mid and oi_delta_pct is not None and oi_delta_pct < 0:
            flow_bias = "outflow"
        elif last >= mid:
            flow_bias = "inflow"
        else:
            flow_bias = "outflow"

    vol_bias = None
    if len(candles_4h) >= 21:
        recent_range = candles_4h[-1]["high"] - candles_4h[-1]["low"]
        avg_range = sum(x["high"] - x["low"] for x in candles_4h[-21:-1]) / 20
        recent_vol = candles_4h[-1]["volume"]
        avg_vol = sum(x["volume"] for x in candles_4h[-21:-1]) / 20
        if recent_range > avg_range * 1.2 and recent_vol > avg_vol * 1.2:
            vol_bias = "expansion"
        elif recent_range < avg_range * 0.8 and recent_vol < avg_vol * 0.8:
            vol_bias = "contraction"

    if history:
        recent_oi = [x.get("oi") for x in history[-6:] if x.get("oi")]
        if len(recent_oi) >= 2 and oi:
            base_oi = recent_oi[0]
            if base_oi:
                try:
                    oi_delta_pct = ((oi - base_oi) / base_oi) * 100
                except ZeroDivisionError:
                    pass

    snapshot = {
        "last": ticker.get("last"),
        "vol24h": ticker.get("vol24h"),
        "oi": oi,
        "ts": datetime.now().isoformat(),
    }
    push_history(state, inst_id, snapshot)

    return {
        "fundingRate": funding.get("fundingRate"),
        "nextFundingRate": funding.get("nextFundingRate"),
        "oi": oi,
        "oi_delta_pct": oi_delta_pct,
        "flow_bias": flow_bias,
        "vol_bias": vol_bias,
        "prev_last": prev_last,
        "prev_vol24h": prev_vol24h,
    }


def main():
    client = OKXPublicClient()
    reports = []
    state = load_state()

    for inst_id in WATCHLIST:
        ticker = client.get_ticker(inst_id)
        candles_1h = client.get_candles(inst_id, BAR_MAP["1H"])
        candles_4h = client.get_candles(inst_id, BAR_MAP["4H"])
        candles_1d = client.get_candles(inst_id, BAR_MAP["1D"])
        market_extras = calc_market_extras(client, inst_id, ticker, candles_4h, state)

        trend_1h = analyze_trend(candles_1h)
        trend_4h = analyze_trend(candles_4h)
        trend_1d = analyze_trend(candles_1d)
        plan_1h = build_trade_plan(candles_1h, market_extras)
        plan_4h = build_trade_plan(candles_4h, market_extras)

        reports.append(build_symbol_report(inst_id, ticker, trend_1h, trend_4h, trend_1d, plan_1h, plan_4h))

    save_state(state)
    print(build_report(reports))


if __name__ == "__main__":
    main()
