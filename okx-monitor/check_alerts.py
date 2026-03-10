from __future__ import annotations

from config import WATCHLIST, BAR_MAP
from okx_public import OKXPublicClient
from strategy import build_trade_plan
from main import calc_market_extras
from state import load_state, save_state
from alerts import build_alert


def main():
    client = OKXPublicClient()
    state = load_state()
    alerts = []

    for inst_id in WATCHLIST:
        ticker = client.get_ticker(inst_id)
        candles_1h = client.get_candles(inst_id, BAR_MAP["1H"])
        candles_4h = client.get_candles(inst_id, BAR_MAP["4H"])
        extras = calc_market_extras(client, inst_id, ticker, candles_4h, state)
        plan_1h = build_trade_plan(candles_1h, extras)
        plan_4h = build_trade_plan(candles_4h, extras)
        alert = build_alert(inst_id, ticker.get("last") or 0, plan_1h) or build_alert(inst_id, ticker.get("last") or 0, plan_4h)
        if alert:
            alerts.append(alert)

    save_state(state)
    if alerts:
        print("\n\n".join(alerts))
    else:
        print("NO_ALERTS")


if __name__ == "__main__":
    main()
