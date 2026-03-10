from __future__ import annotations


def fmt(v):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)


def build_symbol_report(inst_id: str, ticker: dict, trend_4h: dict, trend_1d: dict, plan_4h: dict):
    boll = plan_4h.get('boll') or {}
    reasons = '；'.join(plan_4h.get('reasons', [])) if plan_4h.get('reasons') else '-'
    lines = [
        f"{inst_id}",
        f"- 现价：{fmt(ticker.get('last'))}",
        f"- 24H 区间：{fmt(ticker.get('low24h'))} ~ {fmt(ticker.get('high24h'))}",
        f"- 4H 结构：{trend_4h.get('bias')}（MA20={fmt(trend_4h.get('ma20'))} / MA60={fmt(trend_4h.get('ma60'))}）",
        f"- 1D 结构：{trend_1d.get('bias')}（MA20={fmt(trend_1d.get('ma20'))} / MA60={fmt(trend_1d.get('ma60'))}）",
        f"- RSI(14)：{fmt(plan_4h.get('rsi14'))}",
        f"- Boll：下轨={fmt(boll.get('lower'))} / 中轨={fmt(boll.get('mid'))} / 上轨={fmt(boll.get('upper'))}",
        f"- Volume：当前={fmt(plan_4h.get('last_vol'))} / 20均量={fmt(plan_4h.get('avg_vol20'))}",
        f"- MACD：{fmt(plan_4h.get('macd'))}",
        f"- 资金费率：{fmt(plan_4h.get('fundingRate'))}",
        f"- OI：{fmt(plan_4h.get('oi'))} | OI变化：{fmt(plan_4h.get('oi_delta_pct'))}%",
        f"- 资金流倾向：{plan_4h.get('flow_bias') or '-'} | 波动量能：{plan_4h.get('vol_bias') or '-'}",
        f"- 综合信号：{plan_4h.get('signal')}（评分 {fmt(plan_4h.get('score'))}）",
        f"- 信号依据：{reasons}",
        f"- 支撑 / 压力：{fmt(plan_4h.get('support'))} / {fmt(plan_4h.get('resistance'))}",
        f"- 4H 多头触发：{fmt(plan_4h.get('trigger_long'))}",
        f"- 4H 空头触发：{fmt(plan_4h.get('trigger_short'))}",
        f"- 多头止损参考：{fmt(plan_4h.get('stop_long'))}",
        f"- 空头止损参考：{fmt(plan_4h.get('stop_short'))}",
        f"- 结论：{plan_4h.get('summary', '-')}",
    ]
    return "\n".join(lines)


def build_report(items: list[str]):
    header = "OKX 行情策略简报\n"
    footer = "\n\n提示：当前为公共行情规则版，仅做监控和策略参考，不构成自动交易指令。"
    return header + "\n\n".join(items) + footer
