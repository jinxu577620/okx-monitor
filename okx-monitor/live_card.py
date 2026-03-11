from __future__ import annotations

from config import WATCHLIST, BAR_MAP
from okx_public import OKXPublicClient
from main import calc_market_extras
from state import load_state, save_state
from strategy import build_trade_plan, weighted_decision


def decide_side(decision_signal: str, plan_4h: dict):
    if decision_signal in ("强多", "偏多"):
        return "偏多", {
            "entry": plan_4h.get("trigger_long"),
            "tp1": plan_4h.get("tp1_long"),
            "tp2": plan_4h.get("tp2_long"),
            "sl": plan_4h.get("stop_long"),
            "invalid": f"跌回 {plan_4h.get('support')} 下方且量能转弱",
        }
    if decision_signal in ("强空", "偏空"):
        return "偏空", {
            "entry": plan_4h.get("trigger_short"),
            "tp1": plan_4h.get("tp1_short"),
            "tp2": plan_4h.get("tp2_short"),
            "sl": plan_4h.get("stop_short"),
            "invalid": f"重新站回 {plan_4h.get('resistance')} 上方并放量",
        }
    return "观望", {
        "entry": None,
        "tp1": None,
        "tp2": None,
        "sl": None,
        "invalid": "等待关键位突破后再动作",
    }


def build_live_card():
    client = OKXPublicClient()
    state = load_state()
    blocks = ["实时策略测试卡片", ""]

    for inst_id in WATCHLIST:
        ticker = client.get_ticker(inst_id)
        candles_1h = client.get_candles(inst_id, BAR_MAP["1H"])
        candles_4h = client.get_candles(inst_id, BAR_MAP["4H"])
        candles_1d = client.get_candles(inst_id, BAR_MAP["1D"])
        extras = calc_market_extras(client, inst_id, ticker, candles_4h, state)
        plan_1h = build_trade_plan(candles_1h, extras)
        plan_4h = build_trade_plan(candles_4h, extras)
        plan_1d = build_trade_plan(candles_1d, extras)
        decision = weighted_decision(plan_1h, plan_4h, plan_1d)
        bias, trade = decide_side(decision["signal"], plan_4h)

        blocks.extend([
            inst_id,
            f"- 实时价格：{ticker['last']}",
            f"- 当前结论：{bias}（综合分 {decision['weighted_score']}）",
            f"- 主方案开仓点：{trade['entry']}",
            f"- 主方案止盈1：{trade['tp1']}",
            f"- 主方案止盈2：{trade['tp2']}",
            f"- 主方案止损：{trade['sl']}",
            f"- 备用多头触发：{plan_4h.get('trigger_long')} | 止盈 {plan_4h.get('tp1_long')}、{plan_4h.get('tp2_long')} | 止损 {plan_4h.get('stop_long')}",
            f"- 备用空头触发：{plan_4h.get('trigger_short')} | 止盈 {plan_4h.get('tp1_short')}、{plan_4h.get('tp2_short')} | 止损 {plan_4h.get('stop_short')}",
            f"- 失效条件：{trade['invalid']}",
            "",
        ])

    save_state(state)
    return "\n".join(blocks).strip()


if __name__ == "__main__":
    print(build_live_card())
