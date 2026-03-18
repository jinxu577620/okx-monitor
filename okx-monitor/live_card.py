from __future__ import annotations

from config import WATCHLIST, BAR_MAP
from okx_public import OKXPublicClient
from main import calc_market_extras
from state import load_state, save_state
from strategy import build_trade_plan, weighted_decision


def decide_side(decision_signal: str, plan_4h: dict):
    if decision_signal in ("强多", "偏多"):
        return "偏多", {
            "breakout": {
                "entry": plan_4h.get("trigger_long"),
                "tp1": plan_4h.get("tp1_long"),
                "tp2": plan_4h.get("tp2_long"),
                "sl": plan_4h.get("stop_long"),
                "invalid": f"跌回 {plan_4h.get('support')} 下方且量能转弱",
            },
            "pullback": {
                "entry": plan_4h.get("pullback_long_entry"),
                "tp1": plan_4h.get("pullback_long_tp1"),
                "tp2": plan_4h.get("pullback_long_tp2"),
                "sl": plan_4h.get("pullback_long_stop"),
                "invalid": f"回踩 {plan_4h.get('support')} 一带后继续失守",
            },
        }
    if decision_signal in ("强空", "偏空"):
        return "偏空", {
            "breakdown": {
                "entry": plan_4h.get("trigger_short"),
                "tp1": plan_4h.get("tp1_short"),
                "tp2": plan_4h.get("tp2_short"),
                "sl": plan_4h.get("stop_short"),
                "invalid": f"重新站回 {plan_4h.get('resistance')} 上方并放量",
            },
            "rebound": {
                "entry": plan_4h.get("rebound_short_entry"),
                "tp1": plan_4h.get("rebound_short_tp1"),
                "tp2": plan_4h.get("rebound_short_tp2"),
                "sl": plan_4h.get("rebound_short_stop"),
                "invalid": f"反抽 {plan_4h.get('resistance')} 一带后继续上破",
            },
        }
    return "观望", {
        "breakout": {
            "entry": None,
            "tp1": None,
            "tp2": None,
            "sl": None,
            "invalid": "等待关键位突破后再动作",
        },
        "pullback": {
            "entry": None,
            "tp1": None,
            "tp2": None,
            "sl": None,
            "invalid": "等待回踩支撑或反抽压力后再动作",
        },
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
        ])

        if bias == "偏多":
            blocks.extend([
                f"- 突破开多：{trade['breakout']['entry']} | 止盈 {trade['breakout']['tp1']}、{trade['breakout']['tp2']} | 止损 {trade['breakout']['sl']}",
                f"- 回踩开多：{trade['pullback']['entry']} | 止盈 {trade['pullback']['tp1']}、{trade['pullback']['tp2']} | 止损 {trade['pullback']['sl']}",
                f"- 突破失效：{trade['breakout']['invalid']}",
                f"- 回踩失效：{trade['pullback']['invalid']}",
                f"- 备用开空：{plan_4h.get('trigger_short')} | 止盈 {plan_4h.get('tp1_short')}、{plan_4h.get('tp2_short')} | 止损 {plan_4h.get('stop_short')}",
                "",
            ])
        elif bias == "偏空":
            blocks.extend([
                f"- 破位开空：{trade['breakdown']['entry']} | 止盈 {trade['breakdown']['tp1']}、{trade['breakdown']['tp2']} | 止损 {trade['breakdown']['sl']}",
                f"- 反抽开空：{trade['rebound']['entry']} | 止盈 {trade['rebound']['tp1']}、{trade['rebound']['tp2']} | 止损 {trade['rebound']['sl']}",
                f"- 破位失效：{trade['breakdown']['invalid']}",
                f"- 反抽失效：{trade['rebound']['invalid']}",
                f"- 备用开多：{plan_4h.get('trigger_long')} | 止盈 {plan_4h.get('tp1_long')}、{plan_4h.get('tp2_long')} | 止损 {plan_4h.get('stop_long')}",
                "",
            ])
        else:
            blocks.extend([
                f"- 突破开多：{plan_4h.get('trigger_long')} | 止盈 {plan_4h.get('tp1_long')}、{plan_4h.get('tp2_long')} | 止损 {plan_4h.get('stop_long')}",
                f"- 回踩开多：{plan_4h.get('pullback_long_entry')} | 止盈 {plan_4h.get('pullback_long_tp1')}、{plan_4h.get('pullback_long_tp2')} | 止损 {plan_4h.get('pullback_long_stop')}",
                f"- 破位开空：{plan_4h.get('trigger_short')} | 止盈 {plan_4h.get('tp1_short')}、{plan_4h.get('tp2_short')} | 止损 {plan_4h.get('stop_short')}",
                f"- 反抽开空：{plan_4h.get('rebound_short_entry')} | 止盈 {plan_4h.get('rebound_short_tp1')}、{plan_4h.get('rebound_short_tp2')} | 止损 {plan_4h.get('rebound_short_stop')}",
                "",
            ])

    save_state(state)
    return "\n".join(blocks).strip()


if __name__ == "__main__":
    print(build_live_card())
