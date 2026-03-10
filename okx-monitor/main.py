from config import WATCHLIST, BAR_MAP
from okx_public import OKXPublicClient
from report import build_symbol_report, build_report
from strategy import analyze_trend, build_trade_plan


def main():
    client = OKXPublicClient()
    reports = []

    for inst_id in WATCHLIST:
        ticker = client.get_ticker(inst_id)
        candles_4h = client.get_candles(inst_id, BAR_MAP["4H"])
        candles_1d = client.get_candles(inst_id, BAR_MAP["1D"])

        trend_4h = analyze_trend(candles_4h)
        trend_1d = analyze_trend(candles_1d)
        plan_4h = build_trade_plan(candles_4h)

        reports.append(build_symbol_report(inst_id, ticker, trend_4h, trend_1d, plan_4h))

    print(build_report(reports))


if __name__ == "__main__":
    main()
