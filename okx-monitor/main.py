from config import WATCHLIST, BAR_MAP
from okx_public import OKXPublicClient
from report import build_symbol_report, build_report
from strategy import analyze_trend, build_trade_plan


def calc_market_extras(client: OKXPublicClient, inst_id: str, ticker: dict):
    funding = client.get_funding_rate(inst_id)
    oi_now = client.get_open_interest(inst_id)
    oi_later = client.get_open_interest(inst_id)

    oi = oi_now.get("oi")
    oi_delta_pct = None
    if oi and oi_later.get("oi"):
        try:
            oi_delta_pct = ((oi_now["oi"] - oi_later["oi"]) / oi_later["oi"]) * 100
        except ZeroDivisionError:
            oi_delta_pct = None

    flow_bias = None
    last = ticker.get("last")
    bid = ticker.get("bidPx")
    ask = ticker.get("askPx")
    if last and bid and ask:
        mid = (bid + ask) / 2
        if last >= mid:
            flow_bias = "inflow"
        else:
            flow_bias = "outflow"

    return {
        "fundingRate": funding.get("fundingRate"),
        "oi": oi_now.get("oi"),
        "oi_delta_pct": oi_delta_pct,
        "flow_bias": flow_bias,
    }


def main():
    client = OKXPublicClient()
    reports = []

    for inst_id in WATCHLIST:
        ticker = client.get_ticker(inst_id)
        candles_4h = client.get_candles(inst_id, BAR_MAP["4H"])
        candles_1d = client.get_candles(inst_id, BAR_MAP["1D"])
        market_extras = calc_market_extras(client, inst_id, ticker)

        trend_4h = analyze_trend(candles_4h)
        trend_1d = analyze_trend(candles_1d)
        plan_4h = build_trade_plan(candles_4h, market_extras)

        reports.append(build_symbol_report(inst_id, ticker, trend_4h, trend_1d, plan_4h))

    print(build_report(reports))


if __name__ == "__main__":
    main()
